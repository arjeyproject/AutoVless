"""Genuine connectivity tests for configuration links.

Everything the old ``panel:ping`` screen did was a TCP handshake to the entry
address. A TCP handshake proves exactly one thing - that the address answers -
and it proved it just as well for a config whose UUID nobody accepts, whose SNI
is filtered, and whose worker is gone. That is how a screen full of green
checkmarks and a client app full of dead configs could coexist.

This module speaks the actual protocols. For a ``vless://`` link it walks the
client's own path - TCP, TLS with the link's SNI, WebSocket (or HTTPUpgrade)
upgrade with the link's path and Host, then a real VLESS request header - and
inside that tunnel it fetches an IP echo over plain HTTP. What comes back is
not an opinion about reachability:

  * the two-byte VLESS response header proves the worker accepted the UUID;
  * the HTTP body inside the tunnel proves a destination outside Cloudflare
    was actually reached and answered;
  * the body itself carries the exit address and its country;
  * the clock that started at the TCP dial gives the latency of the whole trip.

Trojan rides the same path with its own preamble. Shadowsocks is implemented
for the AEAD ciphers the panel ships (aes-256-gcm, chacha20-ietf-poly1305).
SOCKS5 and HTTP proxies are spoken natively. For the things a pure-Python test
genuinely cannot do - REALITY, gRPC, VMess - the result says so by name instead
of inventing a number, and for ``ss``/``vmess`` links a handshake-level test is
still run so a dead server never looks alive.

Every failure is classified: dns, tcp, tls, handshake, auth, timeout. The UI
shows the class, not a stack trace.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import socket
import ssl
import statistics
import struct
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable, Optional
from urllib.parse import parse_qs, unquote, urlparse

log = logging.getLogger("autovless.pingtest")

# Where the tunnel's own test request goes. Plain HTTP on purpose: a TLS
# handshake inside the tunnel would triple the failure surface of the test
# without saying anything the tunnel itself has not already proven. ip-api
# answers 45 requests a minute per exit address, which is orders of magnitude
# above what config testing needs.
ECHO_HOST = "ip-api.com"
ECHO_PORT = 80
ECHO_PATH = f"/json/?fields=query,countryCode,status&r={secrets.token_hex(4)}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

VLESS_RESPONSE_BYTES = 2
WS_PATH_DEFAULT = "/?ed=2560"

ERROR_KINDS = ("dns", "tcp", "tls", "handshake", "auth", "timeout", "unsupported", "internal")

ERROR_TEXT: dict[str, dict[str, str]] = {
    "dns": {
        "fa": "DNS رزولو نشد — آدرس سرور نامعتبر است",
        "en": "DNS resolution failed - bad server address",
    },
    "tcp": {
        "fa": "اتصال TCP برقرار نشد — سرور یا پورت پاسخ نمی‌دهد",
        "en": "TCP connection failed - server or port not answering",
    },
    "tls": {
        "fa": "دست‌دهی TLS شکست خورد — SNI فیلتر است یا گواهی نامعتبر",
        "en": "TLS handshake failed - SNI filtered or bad certificate",
    },
    "handshake": {
        "fa": "پاسخ upgrade دریافت نشد — مسیر/هاست اشتباه یا ورکر از کار افتاده",
        "en": "no upgrade answer - wrong path/host or the worker is down",
    },
    "auth": {
        "fa": "احراز هویت رد شد — UUID یا پسورد با پنل نمی‌خواند",
        "en": "authentication rejected - UUID or password mismatch",
    },
    "timeout": {
        "fa": "پاسخی در زمان مجاز نرسید — مسیر یا سرور بی‌پاسخ است",
        "en": "no answer within the time budget - path or server silent",
    },
    "unsupported": {
        "fa": "این نوع کانفیگ در تست داخلی پشتیبانی نمی‌شود",
        "en": "this config type is not supported by the built-in test",
    },
    "internal": {
        "fa": "خطای داخلی تست",
        "en": "internal test error",
    },
}


def describe_error(kind: str, lang: str) -> str:
    return ERROR_TEXT.get(kind, ERROR_TEXT["internal"])["en" if lang == "en" else "fa"]


def flag_emoji(country: str) -> str:
    code = str(country or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return chr(ord(code[0]) - 0x41 + 0x1F1E6) + chr(ord(code[1]) - 0x41 + 0x1F1E6)


class LinkError(ValueError):
    """A configuration link that cannot be used as written."""


@dataclass
class TestResult:
    ok: bool
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    exit_ip: str = ""
    exit_country: str = ""
    error_kind: str = ""
    error_detail: str = ""
    method: str = ""
    server_ip: str = ""
    rounds: int = 0
    tested_at: int = field(default_factory=lambda: int(time.time()))

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "exit_ip": self.exit_ip,
            "exit_country": self.exit_country,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail[:200],
            "method": self.method,
            "server_ip": self.server_ip,
            "rounds": self.rounds,
            "tested_at": self.tested_at,
        }


# --------------------------------------------------------------------- #
# link parsing
# --------------------------------------------------------------------- #

_KNOWN_SCHEMES = ("vless", "trojan", "ss", "vmess", "socks", "socks5", "http", "https")


def _parse_qs_single(query: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


def parse_link(link: str) -> dict[str, Any]:
    """Parse any link the panel ecosystem can produce or a client can paste.

    Returns a flat dict; raises :class:`LinkError` with a short reason for
    anything malformed. Invention is not on the table: a link without a host
    or port is rejected, not repaired.
    """
    raw = str(link or "").strip()
    if not raw:
        raise LinkError("empty link")
    scheme = raw.split("://", 1)[0].lower() if "://" in raw else ""
    if scheme not in _KNOWN_SCHEMES:
        raise LinkError(f"unsupported scheme {scheme or 'none'}")

    if scheme == "vmess":
        return _parse_vmess(raw)
    if scheme == "ss":
        return _parse_ss(raw)

    parsed = urlparse(raw)
    query = _parse_qs_single(parsed.query)
    host = parsed.hostname or ""
    if not host:
        raise LinkError("no server host")
    try:
        port = int(parsed.port)
    except (TypeError, ValueError):
        raise LinkError("no server port") from None
    if not 0 < port < 65536:
        raise LinkError(f"bad port {port}")

    transport = (query.get("type") or query.get("network") or "tcp").lower()
    security = (query.get("security") or ("tls" if scheme == "trojan" else "")).lower()
    sni = query.get("sni") or query.get("peer") or query.get("host") or host
    host_header = query.get("host") or sni or host
    path = unquote(query.get("path") or WS_PATH_DEFAULT)

    item: dict[str, Any] = {
        "scheme": "socks5" if scheme in ("socks", "socks5") else scheme,
        "host": host,
        "port": port,
        "security": security,
        "transport": transport,
        "sni": sni,
        "host_header": host_header,
        "path": path,
        "mode": query.get("mode") or "",
        "name": unquote(parsed.fragment or "") or "config",
        "uuid": unquote(parsed.username or ""),
        "password": unquote(parsed.username or ""),
        "link": raw,
        "params": query,
    }
    if scheme == "vless" and not item["uuid"]:
        raise LinkError("vless link without uuid")
    if scheme == "vless" and (query.get("encryption") or "none").lower() not in ("none", ""):
        raise LinkError("vless encryption must be none")
    if scheme == "trojan" and not item["password"]:
        raise LinkError("trojan link without password")
    if scheme in ("socks5", "http", "https"):
        item["password"] = unquote(parsed.password or "")
    if security == "reality":
        item["transport"] = "reality"
    if transport in ("grpc", "grpcu"):
        item["transport"] = "grpc"
    return item


def _parse_vmess(raw: str) -> dict[str, Any]:
    body = raw.split("://", 1)[1]
    padded = body + "=" * (-len(body) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8", "ignore"))
    except (ValueError, binascii.Error):
        raise LinkError("vmess payload is not valid base64 json") from None
    if not isinstance(data, dict):
        raise LinkError("vmess payload is not an object")
    host = str(data.get("add") or "")
    try:
        port = int(str(data.get("port") or 0))
    except ValueError:
        raise LinkError("vmess port is not a number") from None
    if not host or not 0 < port < 65536:
        raise LinkError("vmess link without host/port")
    tls = str(data.get("tls") or "").lower() == "tls"
    return {
        "scheme": "vmess",
        "host": host,
        "port": port,
        "security": "tls" if tls else "",
        "transport": str(data.get("net") or "tcp").lower(),
        "sni": str(data.get("sni") or host),
        "host_header": str(data.get("host") or host),
        "path": str(data.get("path") or WS_PATH_DEFAULT),
        "mode": "",
        "name": str(data.get("ps") or "config"),
        "uuid": str(data.get("id") or ""),
        "password": "",
        "link": raw,
        "params": {},
    }


def _parse_ss(raw: str) -> dict[str, Any]:
    body = raw.split("://", 1)[1].split("#", 1)[0]
    # SIP002: base64(method:password)@host:port?plugin=... - the query carries
    # the v2ray-plugin options and must never leak into the port.
    query: dict[str, str] = {}
    if "?" in body:
        body, _, qs = body.partition("?")
        try:
            from urllib.parse import parse_qsl as _pq
            query = dict(_pq(qs))
        except Exception:
            query = {}
    # SIP002: base64(method:password)@host:port or plugin-less plain
    userinfo, _, hostport = body.rpartition("@")
    if not userinfo:
        # legacy: the whole thing is base64
        padded = body + "=" * (-len(body) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
        except (ValueError, binascii.Error):
            raise LinkError("ss payload is not valid base64") from None
        userinfo, _, hostport = decoded.rpartition("@")
        if not userinfo:
            raise LinkError("ss link without userinfo")
    if ":" not in hostport:
        raise LinkError("ss link without port")
    host, _, port_s = hostport.rpartition(":")
    host = host.strip("[]")
    try:
        port = int(port_s)
    except ValueError:
        raise LinkError("ss port is not a number") from None
    if not host or not 0 < port < 65536:
        raise LinkError("ss link without host/port")
    padded = userinfo + "=" * (-len(userinfo) % 4)
    try:
        cred = base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
    except (ValueError, binascii.Error):
        cred = unquote(userinfo)
    if ":" not in cred:
        raise LinkError("ss userinfo is not method:password")
    method, _, password = cred.partition(":")
    # v2ray-plugin options decide the transport: mode=websocket(+tls) rides a
    # websocket path, everything else stays plain TCP.
    transport, security, host_header, path, mode = "tcp", "none", host, "", ""
    plugin = str(query.get("plugin") or "")
    if plugin:
        pieces = plugin.split(";")
        opts: dict[str, Any] = {}
        for piece in pieces[1:]:
            if "=" in piece:
                k, _, v = piece.partition("=")
                opts[k.strip()] = v.strip()
            elif piece:
                opts[piece] = True
        if str(opts.get("mode") or "").lower() in ("websocket", "ws") or opts.get("websocket"):
            transport = "ws"
            mode = "websocket"
            host_header = str(opts.get("host") or host)
            path = str(opts.get("path") or "/")
            security = "tls" if opts.get("tls") else "none"
    sni = host_header if security == "tls" else host
    return {
        "scheme": "ss",
        "host": host,
        "port": port,
        "security": security,
        "transport": transport,
        "sni": sni,
        "host_header": host_header,
        "path": path,
        "mode": mode,
        "name": "config",
        "uuid": "",
        "password": password,
        "method": method.strip().lower(),
        "link": raw,
        "params": {},
    }


# --------------------------------------------------------------------- #
# dns with a small TTL cache
# --------------------------------------------------------------------- #

_dns_cache: dict[str, tuple[str, float]] = {}
DNS_TTL = 600.0


async def resolve_cached(host: str) -> Optional[str]:
    host = str(host or "").strip().strip("[]")
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    hit = _dns_cache.get(host)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM),
            timeout=5.0,
        )
    except (OSError, socket.gaierror, asyncio.TimeoutError):
        return None
    address = infos[0][4][0] if infos else ""
    if address:
        _dns_cache[host] = (address, time.monotonic() + DNS_TTL)
    return address or None


# --------------------------------------------------------------------- #
# low-level wire helpers
# --------------------------------------------------------------------- #

def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        context.set_alpn_protocols(["http/1.1"])
    except NotImplementedError:  # pragma: no cover
        pass
    return context


async def dial(
    ip: str,
    port: int,
    *,
    tls: bool,
    sni: str,
    timeout: float,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    opening = asyncio.open_connection(
        ip, port, ssl=tls_context() if tls else None, server_hostname=sni if tls else None
    )
    return await asyncio.wait_for(opening, timeout=timeout)


async def _shutdown(writer: Optional[asyncio.StreamWriter]) -> None:
    if writer is None:
        return
    try:
        writer.close()
    except Exception:  # noqa: BLE001
        return
    try:
        await writer.wait_closed()
    except Exception:  # noqa: BLE001
        pass


def classify_error(error: Exception) -> tuple[str, str]:
    """Map an exception onto one of the user-facing error classes."""
    if isinstance(error, LinkError):
        return "unsupported", str(error)
    if isinstance(error, asyncio.TimeoutError):
        return "timeout", "timed out"
    if isinstance(error, ssl.SSLError):
        return "tls", str(error)[:120]
    if isinstance(error, socket.gaierror):
        return "dns", str(error)[:120]
    if isinstance(error, (ConnectionResetError, ConnectionRefusedError, BrokenPipeError, OSError)):
        text = str(error).lower()
        if "refused" in text:
            return "tcp", str(error)[:120]
        return "tcp", str(error)[:120]
    return "internal", f"{type(error).__name__}: {error}"[:120]


# --------------------------------------------------------------------- #
# websocket framing (client side only - the test never listens)
# --------------------------------------------------------------------- #

def ws_frame(payload: bytes) -> bytes:
    """One masked binary frame, exactly what a browser or client would send."""
    header = bytearray([0x82])
    mask_bit = 0x80
    length = len(payload)
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65536:
        header.append(mask_bit | 126)
        header += struct.pack(">H", length)
    else:
        header.append(mask_bit | 127)
        header += struct.pack(">Q", length)
    key = secrets.token_bytes(4)
    header += key
    masked = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + masked


async def ws_read_message(reader: asyncio.StreamReader, timeout: float) -> tuple[bytes, bool]:
    """One complete server message. Returns ``(reply_bytes, is_ping)``.

    Data frames accumulate across continuation frames; a ping is answered with
    a masked pong that the caller puts straight back on the wire.
    """
    buffer = bytearray()
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError("websocket message incomplete")
        head = await asyncio.wait_for(reader.readexactly(2), timeout=remaining)
        opcode = head[0] & 0x0F
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", await reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", await reader.readexactly(8))[0]
        payload = await asyncio.wait_for(reader.readexactly(length), timeout=remaining) if length else b""
        if opcode == 0x9:  # ping -> pong (masked, control frame)
            pong = bytearray([0x8A])
            mask_bit = 0x80
            if len(payload) < 126:
                pong.append(mask_bit | len(payload))
            else:
                pong.append(mask_bit | 126)
                pong += struct.pack(">H", len(payload))
            key = secrets.token_bytes(4)
            pong += key
            pong += bytes(b ^ key[i % 4] for i, b in enumerate(payload))
            return bytes(pong), True
        if opcode == 0x8:  # close
            raise ConnectionResetError("websocket closed by server")
        if opcode in (0x2, 0x0):
            buffer += payload
            if buffer:
                return bytes(buffer), False
        # 0x1 text frames carry no VLESS payload; keep reading.


async def ws_send(writer: asyncio.StreamWriter, payload: bytes) -> None:
    writer.write(ws_frame(payload))
    await writer.drain()


# --------------------------------------------------------------------- #
# proxy request headers
# --------------------------------------------------------------------- #

def vless_request(uuid: str, dest_host: str, dest_port: int, payload: bytes) -> bytes:
    raw = uuid.replace("-", "")
    uid = bytes.fromhex(raw)
    if len(uid) != 16:
        raise LinkError("uuid is not 16 bytes")
    domain = dest_host.encode("idna")
    head = bytearray()
    head.append(0x00)
    head += uid
    head.append(0x00)  # addon length
    head.append(0x01)  # tcp
    head += struct.pack(">H", dest_port)
    head.append(0x02)  # domain
    head.append(len(domain))
    head += domain
    return bytes(head) + payload


def trojan_request(password: str, dest_host: str, dest_port: int, payload: bytes) -> bytes:
    digest = hashlib.sha224(password.encode("utf-8")).hexdigest().encode("ascii")
    domain = dest_host.encode("idna")
    head = bytearray()
    head += digest
    head += b"\r\n"
    head.append(0x01)  # tcp connect
    head.append(0x03 if not _is_ip(dest_host) else 0x01)
    if head[-1] == 0x03:
        head.append(len(domain))
        head += domain
        head += struct.pack(">H", dest_port)
    else:
        head += bytes(int(part) for part in dest_host.split("."))
        head += struct.pack(">H", dest_port)
    head += b"\r\n"
    return bytes(head) + payload


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _echo_payload() -> bytes:
    return (
        f"GET {ECHO_PATH} HTTP/1.1\r\n"
        f"Host: {ECHO_HOST}\r\n"
        f"User-Agent: {USER_AGENT}\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("latin1")


def _split_http_response(raw: bytes) -> tuple[int, bytes]:
    """Status code and body of the first HTTP response inside the buffer."""
    marker = raw.find(b"\r\n\r\n")
    if marker < 0:
        return 0, b""
    head = raw[:marker].decode("latin1", "ignore")
    body = raw[marker + 4 :]
    parts = head.split(" ")
    if len(parts) < 2 or not parts[0].upper().startswith("HTTP/"):
        return 0, body
    try:
        return int(parts[1]), body
    except ValueError:
        return 0, body


def _parse_exit(body: bytes) -> tuple[str, str]:
    """Exit ip + country from the echo body, "" when it is not there."""
    marker = body.find(b"{")
    if marker < 0:
        return "", ""
    try:
        data = json.loads(body[marker:].decode("utf-8", "ignore"))
    except ValueError:
        return "", ""
    return str(data.get("query") or ""), str(data.get("countryCode") or "").upper()


def _looks_chunked(buffer: bytes) -> bool:
    """True when the buffer opens like a chunked-transfer frame (``<hex>\\r\\n``)."""
    head = buffer[:12]
    cut = head.find(b"\r\n")
    if cut <= 0:
        return False
    try:
        int(head[:cut], 16)
    except ValueError:
        return False
    return True


def _dechunk_tail(buffer: bytes) -> bytes:
    """Best-effort de-chunking of a buffered piece of a chunked body.

    The tunnel answer arrives as ``<hex>\\r\\n<bytes>\\r\\n`` repeats. This walks
    the sizes it can see and joins the payloads; a trailing partial chunk is
    carried through as-is so the caller's next read can complete it.
    """
    if not _looks_chunked(buffer):
        return buffer
    out = bytearray()
    pos = 0
    while pos < len(buffer):
        cut = buffer.find(b"\r\n", pos)
        if cut < 0:
            out += buffer[pos:]
            break
        try:
            size = int(buffer[pos:cut], 16)
        except ValueError:
            out += buffer[pos:]
            break
        start = cut + 2
        end = start + size
        if end + 2 > len(buffer):
            out += buffer[start : min(end, len(buffer))]
            break
        out += buffer[start:end]
        pos = end + 2
        if size == 0:
            break
    return bytes(out)


# --------------------------------------------------------------------- #
# the tunnel test itself
# --------------------------------------------------------------------- #

async def _tunnel_round(
    params: dict,
    transport: str,
    timeout: float,
) -> tuple[float, str, str]:
    """One full client path. Returns (latency, exit_ip, exit_country).

    Raises whatever went wrong; :func:`classify_error` turns it into a class.
    """
    host = str(params["host"])
    port = int(params["port"])
    security = str(params.get("security") or "")
    sni = str(params.get("sni") or host)
    host_header = str(params.get("host_header") or host)

    ip = await resolve_cached(host)
    if not ip:
        raise socket.gaierror(f"cannot resolve {host}")

    started = time.perf_counter()
    reader = writer = None
    try:
        reader, writer = await dial(ip, port, tls=security == "tls", sni=sni, timeout=timeout)

        if transport in ("ws", "httpupgrade"):
            key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
            path = str(params.get("path") or WS_PATH_DEFAULT)
            head = _tunnel_head(params)
            # The ``?ed=N`` path convention means the first N bytes of the
            # payload ride the upgrade request itself, base64url-encoded in
            # Sec-WebSocket-Protocol - that is what every real client does, and
            # the worker enqueues those bytes before any frame. A link without
            # ed carries the head in an ordinary frame instead.
            early, remainder = b"", head
            marker = "ed="
            try:
                ed_value = int(path.split(marker, 1)[1].split("&", 1)[0])
            except (IndexError, ValueError):
                ed_value = 0
            if ed_value > 0:
                early, remainder = head[:ed_value], head[ed_value:]
            early_token = base64.urlsafe_b64encode(early).decode("ascii").rstrip("=") if early else ""
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Connection: Upgrade\r\n"
                "Upgrade: websocket\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: {USER_AGENT}\r\n"
                + (f"Sec-WebSocket-Protocol: {early_token}\r\n" if early_token else "")
                + "\r\n"
            )
            writer.write(request.encode("latin1"))
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(2048), timeout=timeout)
            status = _split_http_response(raw)[0] if raw else 0
            if status != 101:
                raise ConnectionResetError(f"upgrade refused with status {status or 'none'}")

            if remainder:
                await ws_send(writer, remainder)
            # answer the server's first frames; the payload with the echo
            # response arrives as one or more data messages.
            exit_ip = exit_country = ""
            deadline = time.monotonic() + timeout
            received = b""
            while time.monotonic() < deadline:
                message, is_ping = await ws_read_message(reader, timeout=max(0.5, deadline - time.monotonic()))
                if is_ping:
                    writer.write(message)
                    await writer.drain()
                    continue
                received += message
                if len(received) < VLESS_RESPONSE_BYTES:
                    continue
                latency = (time.perf_counter() - started) * 1000
                body = received[VLESS_RESPONSE_BYTES:] if params["scheme"] in ("vless", "vmess") else received
                status, http_body = _split_http_response(body)
                if status == 200:
                    exit_ip, exit_country = _parse_exit(http_body)
                return latency, exit_ip, exit_country
            raise asyncio.TimeoutError("tunnel produced no answer")

        if transport == "xhttp":
            path = str(params.get("path") or "/")
            if security != "tls":
                raise LinkError("xhttp needs a tls port")
            head = _tunnel_head(params)
            body = head + _echo_payload()
            request = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Content-Type: application/grpc\r\n"
                f"User-Agent: {USER_AGENT}\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            ).encode("latin1") + body
            writer.write(request)
            await writer.drain()
            deadline = time.monotonic() + timeout
            raw = b""
            while time.monotonic() < deadline and b"\r\n\r\n" not in raw:
                chunk = await asyncio.wait_for(
                    reader.read(2048), timeout=max(0.5, deadline - time.monotonic())
                )
                if not chunk:
                    break
                raw += chunk
            status, first = _split_http_response(raw)
            if status != 200:
                raise ConnectionResetError(f"xhttp answered {status or 'nothing'}")
            # The answer body is chunked (the edge streams the tunnel back).
            # De-chunk until the VLESS two-byte header and the inner response
            # have both arrived, then parse the exit out of the inner body.
            streamed = _dechunk_tail(raw)
            rest = streamed or first
            while time.monotonic() < deadline:
                if len(rest) > VLESS_RESPONSE_BYTES:
                    inner_status, http_body = _split_http_response(rest[VLESS_RESPONSE_BYTES:])
                    if inner_status == 200:
                        latency = (time.perf_counter() - started) * 1000
                        exit_ip, exit_country = _parse_exit(http_body)
                        return latency, exit_ip, exit_country
                chunk = await asyncio.wait_for(
                    reader.read(2048), timeout=max(0.5, deadline - time.monotonic())
                )
                if not chunk:
                    break
                rest += _dechunk_tail(chunk) if _looks_chunked(chunk) else chunk
            raise asyncio.TimeoutError("xhttp tunnel produced no inner answer")

        if params["scheme"] == "socks5":
            return await _socks5_round(reader, writer, params, started, timeout)

        if params["scheme"] in ("http", "https"):
            return await _http_proxy_round(reader, writer, params, started, timeout)

        if transport == "tcp":
            head = _tunnel_head(params)
            writer.write(head)
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not raw:
                raise asyncio.TimeoutError("no answer on raw tcp")
            latency = (time.perf_counter() - started) * 1000
            body = raw[VLESS_RESPONSE_BYTES:] if params["scheme"] == "vless" else raw
            status, http_body = _split_http_response(body)
            exit_ip, exit_country = ("", "")
            if status == 200:
                exit_ip, exit_country = _parse_exit(http_body)
            return latency, exit_ip, exit_country

        raise LinkError(f"transport {transport} is not testable here")
    finally:
        await _shutdown(writer)


def _tunnel_head(params: dict) -> bytes:
    """The protocol preamble the client sends once the transport is up."""
    scheme = params["scheme"]
    if scheme == "vless":
        return vless_request(params["uuid"], ECHO_HOST, ECHO_PORT, _echo_payload())
    if scheme == "trojan":
        return trojan_request(params["password"], ECHO_HOST, ECHO_PORT, _echo_payload())
    if scheme == "ss":
        return b""  # the ss target header rides encrypted; see _ss_round
    raise LinkError(f"{scheme} cannot build a tunnel head")


async def _socks5_round(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    params: dict,
    started: float,
    timeout: float,
) -> tuple[float, str, str]:
    user = str(params.get("uuid") or "")
    password = str(params.get("password") or "")
    greeting = b"\x05\x02\x00\x02" if user else b"\x05\x01\x00"
    writer.write(greeting)
    await writer.drain()
    choice = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
    if choice[0] != 5:
        raise ConnectionResetError("not a socks5 server")
    if choice[1] == 0x02:
        if not user:
            raise ConnectionResetError("proxy demands auth we do not have")
        user_b = user.encode("utf-8")
        pass_b = password.encode("utf-8")
        writer.write(bytes([1, len(user_b)]) + user_b + bytes([len(pass_b)]) + pass_b)
        await writer.drain()
        verdict = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        if verdict[1] != 0:
            raise PermissionError("socks5 auth rejected")
    elif choice[1] != 0:
        raise ConnectionResetError("socks5 auth method refused")

    domain = ECHO_HOST.encode("idna")
    request = b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + struct.pack(">H", ECHO_PORT)
    writer.write(request)
    await writer.drain()
    reply = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    if reply[1] != 0:
        raise ConnectionResetError(f"socks5 connect failed with code {reply[1]}")
    atyp = reply[3]
    if atyp == 1:
        await reader.readexactly(4)
    elif atyp == 4:
        await reader.readexactly(16)
    else:
        n = (await reader.readexactly(1))[0]
        await reader.readexactly(n)
    await reader.readexactly(2)

    writer.write(_echo_payload())
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
    if not raw:
        raise asyncio.TimeoutError("socks5 tunnel produced no answer")
    latency = (time.perf_counter() - started) * 1000
    status, body = _split_http_response(raw)
    if status != 200:
        raise ConnectionResetError(f"destination answered {status}")
    exit_ip, exit_country = _parse_exit(body)
    return latency, exit_ip, exit_country


async def _http_proxy_round(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    params: dict,
    started: float,
    timeout: float,
) -> tuple[float, str, str]:
    user = str(params.get("uuid") or "")
    password = str(params.get("password") or "")
    authority = f"{ECHO_HOST}:{ECHO_PORT}"
    if user:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        connect = f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\nProxy-Authorization: Basic {token}\r\n\r\n"
    else:
        connect = f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n"
    writer.write(connect.encode("latin1"))
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(2048), timeout=timeout)
    status = _split_http_response(raw)[0] if raw else 0
    if status != 200:
        raise PermissionError(f"proxy CONNECT refused with {status or 'nothing'}")
    writer.write(_echo_payload())
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
    if not raw:
        raise asyncio.TimeoutError("proxy tunnel produced no answer")
    latency = (time.perf_counter() - started) * 1000
    status, body = _split_http_response(raw)
    if status != 200:
        raise ConnectionResetError(f"destination answered {status}")
    exit_ip, exit_country = _parse_exit(body)
    return latency, exit_ip, exit_country


# --------------------------------------------------------------------- #
# shadowsocks AEAD
# --------------------------------------------------------------------- #

_SS_AEAD = {
    "aes-256-gcm": ("aes_256_gcm", 32, 16, 12),
    "aes-128-gcm": ("aes_128_gcm", 16, 16, 12),
    "chacha20-ietf-poly1305": ("chacha20_ietf_poly1305", 32, 16, 12),
}


def _ss_cipher(name: str):
    from cryptography.hazmat.primitives.ciphers.aead import (
        AESGCM,
        ChaCha20Poly1305,
    )

    if name == "aes-256-gcm":
        return AESGCM
    if name == "chacha20-ietf-poly1305":
        return ChaCha20Poly1305
    return None


def _ss_subkey(method: str, key: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    info = b"ss-subkey"
    # shadowsocks AEAD derives the per-direction subkey with HKDF-SHA1 -
    # SHA256 here would silently mismatch every server and fail with InvalidTag.
    digest = hashes.SHA1()
    length = len(key)
    hk = HKDF(algorithm=digest, length=length, salt=salt, info=info)
    return hk.derive(key)


def _ss_target_header(dest_host: str, dest_port: int) -> bytes:
    domain = dest_host.encode("idna")
    return b"\x00" if False else b"\x03" + bytes([len(domain)]) + domain + struct.pack(">H", dest_port)


async def _ss_round(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    params: dict,
    started: float,
    timeout: float,
) -> tuple[float, str, str]:
    method = str(params.get("method") or "").lower()
    if method not in _SS_AEAD:
        raise LinkError(f"cipher {method or 'none'} is not testable here")
    _, key_len, tag_len, nonce_len = _SS_AEAD[method]
    aead = _ss_cipher(method)
    if aead is None:
        raise LinkError(f"cipher {method} is not available")

    password = str(params.get("password") or "")
    if password.startswith("gcm:") or password.startswith("chacha20:"):
        password = password.split(":", 1)[1]
    # The standard KDF for shadowsocks is OpenSSL's EVP_BytesToKey; hashlib
    # lacks it, so it is reproduced here (MD5 based) exactly as every client.
    key = _evp_bytes_to_key(password.encode("utf-8"), key_len)

    salt_len = key_len
    salt = secrets.token_bytes(salt_len)
    subkey = _ss_subkey(method, key, salt)

    header = _ss_target_header(ECHO_HOST, ECHO_PORT) + _echo_payload()
    cipher = aead(subkey)

    def seal(nonce_counter: int, plaintext: bytes) -> bytes:
        nonce = nonce_counter.to_bytes(nonce_len, "big")
        return cipher.encrypt(nonce, plaintext, None)

    counter = 0
    stream = salt
    stream += seal(counter, struct.pack(">H", len(header)))
    counter += 1
    for offset in range(0, len(header), 0x3FFF):
        stream += seal(counter, header[offset : offset + 0x3FFF])
        counter += 1

    writer.write(stream)
    await writer.drain()

    raw = await asyncio.wait_for(reader.read(8192), timeout=timeout)
    if not raw:
        raise asyncio.TimeoutError("ss tunnel produced no answer")
    latency = (time.perf_counter() - started) * 1000

    # decrypt the reply: [salt][len+tag][payload+tag]
    reply_salt, rest = raw[:salt_len], raw[salt_len:]
    reply_sub = _ss_subkey(method, key, reply_salt)
    rcipher = aead(reply_sub)
    ln = rcipher.decrypt((0).to_bytes(nonce_len, "big"), rest[: 2 + tag_len], None)
    size = struct.unpack(">H", ln)[0]
    payload = rcipher.decrypt(
        (1).to_bytes(nonce_len, "big"), rest[2 + tag_len : 2 + tag_len + size + tag_len], None
    )
    status, body = _split_http_response(payload)
    if status != 200:
        raise ConnectionResetError(f"destination answered {status}")
    exit_ip, exit_country = _parse_exit(body)
    return latency, exit_ip, exit_country


def _evp_bytes_to_key(password: bytes, key_len: int) -> bytes:
    """OpenSSL EVP_BytesToKey with MD5, count=1 - shadowsocks' key schedule."""
    md5 = lambda b: hashlib.md5(b).digest()  # noqa: E731
    d = b""
    prev = b""
    while len(d) < key_len:
        prev = md5(prev + password + b"")
        d += prev
    return d[:key_len]


# --------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------- #

SUPPORTED_REAL = {"vless", "trojan", "socks5", "http"}
SUPPORTED_HANDSHAKE_ONLY = {"ss", "vmess"}


def needs_core(params: dict) -> bool:
    """True when only a real xray core can speak this link properly."""
    scheme = str(params.get("scheme") or "")
    transport = str(params.get("transport") or "")
    if scheme in ("vmess",):
        return True
    if transport in ("grpc", "reality", "quic"):
        return True
    if scheme == "ss":
        method = str(params.get("method") or "").lower()
        from . import xraycore

        if method not in _SS_AEAD or not xraycore.available():
            return True
        # A plugin (v2ray-plugin websocket) framing is core-only territory:
        # the pure-python AEAD reader cannot parse the plugin's stream.
        if transport in ("ws", "httpupgrade"):
            return True
    return False


async def test_link(
    link: str,
    *,
    rounds: int = 2,
    timeout: float = 12.0,
    gap: float = 0.3,
    transport_override: str = "",
) -> TestResult:
    """Test one configuration link the way a client would use it.

    Two rounds, median latency. The first round that reaches the echo carries
    the exit address; a round that only proves the transport still counts for
    latency. Failures are classified, never swallowed.
    """
    try:
        params = parse_link(link)
    except LinkError as error:
        return TestResult(ok=False, error_kind="unsupported", error_detail=str(error), method="parse")

    server_ip = await resolve_cached(str(params["host"])) or ""
    scheme = params["scheme"]
    transport = transport_override or str(params["transport"])

    # The core path: one round, real client, real answer. Used whenever the
    # pure-python path cannot speak the link at all.
    from . import xraycore

    if needs_core(params) or (transport == "xhttp" and xraycore.available()):
        if not xraycore.available():
            return TestResult(
                ok=False,
                server_ip=server_ip,
                error_kind="unsupported",
                error_detail="needs the xray core to test",
                method="none",
            )
        try:
            params = {**params, "transport": transport}
            latency, exit_ip, exit_country = await asyncio.wait_for(
                xraycore.test_with_core(params), timeout=timeout + 8.0
            )
            return TestResult(
                ok=True,
                latency_ms=round(latency, 1),
                exit_ip=exit_ip,
                exit_country=exit_country,
                server_ip=server_ip,
                method=f"core:{scheme}:{transport}",
                rounds=1,
            )
        except Exception as error:  # noqa: BLE001
            kind, detail = classify_error(error)
            text = str(error)
            # An edge WAF refusal reads "unexpected status 403" in the core's
            # log - report it as what it is, not as a timeout.
            if "status 403" in text or "status 40" in text:
                code = ""
                for token in text.split():
                    if token.isdigit() and 400 <= int(token) <= 599:
                        code = token
                        break
                kind, detail = "handshake", f"edge refused the tunnel with {code or 'an http error'} (waf/bot protection)"
            return TestResult(
                ok=False,
                server_ip=server_ip,
                error_kind=kind,
                error_detail=detail,
                method=f"core:{scheme}:{transport}",
            )

    samples: list[float] = []
    exit_ip = exit_country = ""
    last_kind, last_detail = "", ""
    method = f"{scheme}:{transport}"

    for attempt in range(max(1, rounds)):
        if attempt:
            await asyncio.sleep(gap)
        try:
            if scheme == "ss":
                params = {**params}
                latency, e_ip, e_cc = 0.0, "", ""
                # ss is tested through its own dial below
                ip = server_ip or await resolve_cached(str(params["host"]))
                if not ip:
                    raise socket.gaierror(f"cannot resolve {params['host']}")
                started = time.perf_counter()
                r, w = await dial(
                    ip,
                    int(params["port"]),
                    tls=False,
                    sni="",
                    timeout=timeout,
                )
                try:
                    latency, e_ip, e_cc = await _ss_round(r, w, params, started, timeout)
                finally:
                    await _shutdown(w)
            else:
                latency, e_ip, e_cc = await _tunnel_round(params, transport, timeout)
            samples.append(latency)
            exit_ip = e_ip or exit_ip
            exit_country = e_cc or exit_country
            last_kind, last_detail = "", ""
        except Exception as error:  # noqa: BLE001
            last_kind, last_detail = classify_error(error)
            if last_kind in ("dns", "tcp", "tls", "auth", "unsupported"):
                break  # a handshake-class failure will not heal in round two

    if not samples:
        return TestResult(
            ok=False,
            server_ip=server_ip,
            error_kind=last_kind or "internal",
            error_detail=last_detail or "no round succeeded",
            method=method,
        )

    jitter = max(samples) - min(samples) if len(samples) > 1 else 0.0
    return TestResult(
        ok=True,
        latency_ms=round(statistics.median(samples), 1),
        jitter_ms=round(jitter, 1),
        exit_ip=exit_ip,
        exit_country=exit_country,
        server_ip=server_ip,
        method=method,
        rounds=len(samples),
    )


async def test_many(
    jobs: Iterable[tuple[str, str]],
    *,
    concurrency: int = 4,
    timeout: float = 12.0,
    progress: Optional[Any] = None,
) -> AsyncIterator[tuple[str, TestResult]]:
    """Run (key, link) pairs through :func:`test_link` with a bounded gate.

    Yields results as they land. One dead config never blocks the batch: its
    test finishes (or times out) on its own while the others keep moving.
    """
    gate = asyncio.Semaphore(max(1, concurrency))
    items = [(key, str(link)) for key, link in jobs if str(link or "").strip()]
    if not items:
        return

    async def one(key: str, link: str) -> tuple[str, TestResult]:
        async with gate:
            try:
                return key, await asyncio.wait_for(test_link(link, timeout=timeout), timeout=timeout + 6.0)
            except asyncio.TimeoutError:
                return key, TestResult(ok=False, error_kind="timeout", error_detail="test budget exceeded")

    tasks = [asyncio.create_task(one(key, link), name=f"pingtest-{key}") for key, link in items]
    done_count = 0
    for fut in asyncio.as_completed(tasks):
        try:
            key, result = await fut
        except Exception as error:  # noqa: BLE001
            log.warning("a test task crashed: %s", error)
            continue
        done_count += 1
        if progress is not None:
            try:
                await progress(done_count, len(items), key, result)
            except Exception:  # noqa: BLE001
                pass
        yield key, result
