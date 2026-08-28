"""Client-path probes: prove an entry point the way a client will use it.

Every check in here answers one narrow question: if we hand somebody a config
pointing at ``ip:port``, will their app get a tunnel? That is a much stronger
claim than "the address answered a handshake", and the gap between the two is
exactly what shipped five dead TLS configs next to three working plain ones.

The old verification asked every address for ``GET /cdn-cgi/trace`` with the
hostname ``cloudflare.com``. On a plain HTTP port that happens to be almost
precisely what a client sends: same plaintext request, same Host-header routing,
so port 80 verified itself honestly. On a TLS port it is a different
conversation entirely, with a different SNI, a different certificate and a
different origin, and Cloudflare answers it from any edge address whether or not
that address will carry a WebSocket for *your* worker hostname on *that* port.

So the probes here speak the client's sentence instead:

    TCP -> TLS with the panel's own SNI -> GET <ws path> with Upgrade: websocket
        -> and nothing is verified without ``101 Switching Protocols``

``trace()`` survives as the cold-start check for a pool that has no panel
hostname to aim at yet. It is never allowed to stand in for a failed handshake.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import secrets
import ssl
import statistics
import time
from typing import Optional

log = logging.getLogger("autovless.probe")

TRACE_HOST = "cloudflare.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_COLO_TRACE = re.compile(r"(?:^|\n)colo=([A-Za-z]{3,4})", re.I)
_COLO_RAY = re.compile(r"cf-ray:[^\r\n]*-([A-Za-z]{3,4})", re.I)
_NET_ERRORS = (OSError, ssl.SSLError, asyncio.TimeoutError, ValueError)


def tls_context(alpn: str = "http/1.1") -> ssl.SSLContext:
    """A permissive context, on purpose.

    We are not authenticating Cloudflare here, we are measuring whether a TLS
    session to this address, with this SNI, completes at all. Refusing a chain
    would only hide the answer we came for.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        context.set_alpn_protocols([alpn])
    except NotImplementedError:  # pragma: no cover - platform dependent
        pass
    return context


async def _shutdown(writer: Optional[asyncio.StreamWriter]) -> None:
    if writer is None:
        return
    try:
        writer.close()
    except _NET_ERRORS:
        return
    try:
        await writer.wait_closed()
    except _NET_ERRORS:
        pass


async def _dial(ip: str, port: int, timeout: float, tls: bool, sni: str):
    if tls:
        opening = asyncio.open_connection(ip, port, ssl=tls_context(), server_hostname=sni)
    else:
        opening = asyncio.open_connection(ip, port)
    return await asyncio.wait_for(opening, timeout=timeout)


def _colo(text: str, default: str = "CF") -> str:
    for pattern in (_COLO_TRACE, _COLO_RAY):
        found = pattern.search(text)
        if found:
            return found.group(1).upper()
    return default


async def connect_ms(ip: str, port: int, timeout: float) -> Optional[float]:
    """Plain TCP reachability: a cheap first filter, never proof of anything."""
    writer = None
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        return (time.perf_counter() - started) * 1000
    except _NET_ERRORS:
        return None
    finally:
        await _shutdown(writer)


async def websocket(
    ip: str,
    port: int,
    host: str,
    path: str = "/",
    tls: bool = True,
    timeout: float = 6.0,
) -> Optional[dict]:
    """The whole client path: real SNI, real Host header, real upgrade.

    Latency is returned only on ``101``. Anything else, a 400, a 403, a redirect
    to the landing page, an HTML error, a TLS alert, silence, means a client
    would have failed here too, so it is not a config we are willing to ship.
    """
    writer = None
    started = time.perf_counter()
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    request = (
        f"GET {path or '/'} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"User-Agent: {USER_AGENT}\r\n"
        "Accept: */*\r\n"
        "\r\n"
    )
    try:
        reader, writer = await _dial(ip, port, timeout, tls, host)
        writer.write(request.encode("latin1", "ignore"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(2048), timeout=timeout)
    except _NET_ERRORS:
        return None
    finally:
        await _shutdown(writer)

    text = raw.decode("latin1", "ignore")
    head = text[:64].upper()
    if not head.startswith("HTTP/") or " 101" not in head:
        return None
    return {
        "latency": (time.perf_counter() - started) * 1000,
        "colo": _colo(text),
        "method": "ws",
    }


async def trace(
    ip: str,
    port: int,
    tls: bool = True,
    timeout: float = 6.0,
    sni: str = TRACE_HOST,
) -> Optional[dict]:
    """Cold-start check for a pool with no panel hostname to aim at yet.

    Weaker than :func:`websocket` by construction: it proves the edge answers,
    not that your worker is reachable through it.
    """
    writer = None
    started = time.perf_counter()
    request = (
        f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {sni}\r\n"
        f"User-Agent: {USER_AGENT}\r\nConnection: close\r\n\r\n"
    )
    try:
        reader, writer = await _dial(ip, port, timeout, tls, sni)
        writer.write(request.encode("latin1", "ignore"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(8192), timeout=timeout)
    except _NET_ERRORS:
        return None
    finally:
        await _shutdown(writer)

    text = raw.decode("latin1", "ignore")
    if not text.startswith("HTTP/") or not any(code in text[:32] for code in (" 200", " 301", " 302")):
        return None
    return {
        "latency": (time.perf_counter() - started) * 1000,
        "colo": _colo(text),
        "method": "trace",
    }


async def measure(
    ip: str,
    port: int,
    *,
    tls: bool,
    host: Optional[str] = None,
    path: str = "/",
    rounds: int = 3,
    required: Optional[int] = None,
    timeout: float = 6.0,
    gap: float = 0.12,
) -> Optional[dict]:
    """Repeat one probe a few times and keep the median.

    A single sample is a coin toss on a congested path, so an address has to
    answer ``required`` times out of ``rounds`` before it counts. The spread
    between answers is the jitter, which is weighted heavily when scoring:
    a wobbly entry point is worse for a user than a slower steady one.

    Pass ``host`` to run the real client path. Leave it out and the weaker
    trace check is used, which is only ever appropriate for a cold pool.
    """
    rounds = max(1, int(rounds))
    samples: list[float] = []
    colo = "CF"
    method = "ws" if host else "trace"

    for attempt in range(rounds):
        if attempt:
            await asyncio.sleep(gap)
        if host:
            result = await websocket(ip, port, host, path, tls, timeout)
        else:
            result = await trace(ip, port, tls, timeout)
        if result is not None:
            samples.append(float(result["latency"]))
            colo = result.get("colo") or colo

    floor = max(2, rounds - 1) if required is None else int(required)
    if len(samples) < min(floor, rounds):
        return None
    return {
        "latency": round(statistics.median(samples), 1),
        "jitter": round(max(samples) - min(samples), 1),
        "colo": colo,
        "method": method,
        "hits": len(samples),
        "rounds": rounds,
    }
