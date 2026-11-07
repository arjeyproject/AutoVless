"""Xray-core as the fallback engine for everything a pure-Python test cannot speak.

The built-in test in :mod:`bot.pingtest` walks vless/trojan-over-WS itself, but
some protocols genuinely need a real core: XHTTP stream-one (the edge buffers
the request in ways only a streaming client matches), gRPC, REALITY, VMess and
the shadowsocks ciphers beyond AEAD-GCM. When an ``xray`` binary is present the
test builds a real client config around the link, dials through it as a SOCKS5
client, and measures the same things the native path measures: latency, exit
address, exit country.

The same builder produces the multi-hop chain configs for the Proxy Chain
feature, so the chain test and the chain export can never drift apart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import struct
import secrets
import base64
from typing import Any, Optional

log = logging.getLogger("autovless.xraycore")

_BIN_CACHE: Optional[str] = None


def find_binary() -> str:
    """Locate the xray binary once. "" when there is none."""
    global _BIN_CACHE
    if _BIN_CACHE is not None:
        return _BIN_CACHE
    candidates = [
        os.getenv("XRAY_BIN") or "",
        "/usr/local/bin/xray",
        "/usr/bin/xray",
        "/app/bin/xray",
    ]
    for path in shutil.which("xray"), *candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            _BIN_CACHE = path
            return path
    _BIN_CACHE = ""
    return ""


def available() -> bool:
    return bool(find_binary())


# --------------------------------------------------------------------- #
# outbound config builders
# --------------------------------------------------------------------- #

def _tls_stream(params: dict, transport: str) -> dict:
    security = str(params.get("security") or "")
    sni = str(params.get("sni") or params.get("host") or "")
    stream: dict[str, Any] = {"network": transport}
    if security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = {
            "serverName": sni,
            "allowInsecure": True,
            "fingerprint": str(params.get("params", {}).get("fp") or "chrome"),
        }
    elif security == "reality":
        stream["security"] = "reality"
        reality = {
            "serverName": sni,
            "fingerprint": str(params.get("params", {}).get("fp") or "chrome"),
            "show": False,
        }
        public_key = str(params.get("params", {}).get("pbk") or "")
        if public_key:
            reality["publicKey"] = public_key
        short_id = str(params.get("params", {}).get("sid") or "")
        if short_id:
            reality["shortId"] = short_id
        stream["realitySettings"] = reality
    else:
        stream["security"] = "none"
    return stream


def _ws_settings(params: dict, transport: str) -> dict:
    path = str(params.get("path") or "/")
    settings: dict[str, Any] = {"path": path}
    host = str(params.get("host_header") or "")
    if host:
        settings["headers"] = {"Host": host}
    return settings


def outbound_from_params(params: dict, tag: str) -> dict:
    """One parsed link -> one xray outbound. Raises ValueError for the unknown."""
    scheme = str(params.get("scheme") or "")
    transport = str(params.get("transport") or "tcp")

    if scheme == "socks5":
        settings: dict[str, Any] = {
            "servers": [{
                "address": str(params["host"]),
                "port": int(params["port"]),
            }]
        }
        if params.get("uuid"):
            settings["servers"][0]["users"] = [{
                "user": str(params["uuid"]),
                "pass": str(params.get("password") or ""),
            }]
        return {"tag": tag, "protocol": "socks", "settings": settings}

    if scheme in ("http", "https"):
        server: dict[str, Any] = {
            "address": str(params["host"]),
            "port": int(params["port"]),
        }
        if params.get("uuid"):
            server["users"] = [{
                "user": str(params["uuid"]),
                "pass": str(params.get("password") or ""),
            }]
        return {"tag": tag, "protocol": "http", "settings": {"servers": [server]}}

    if scheme == "ss":
        out = {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": str(params["host"]),
                    "port": int(params["port"]),
                    "method": str(params.get("method") or "aes-256-gcm"),
                    "password": str(params.get("password") or ""),
                }]
            },
        }
        # v2ray-plugin rides SIP003: the core dials the websocket itself via
        # plugin options, streamSettings would only describe a bare TCP dial.
        if str(params.get("transport") or "tcp") == "ws":
            host_header = str(params.get("host_header") or params["host"])
            opts: dict[str, Any] = {"mode": "websocket", "host": host_header, "path": str(params.get("path") or "/ss")}
            if str(params.get("security") or "") == "tls":
                opts["tls"] = True
                opts["serverName"] = str(params.get("sni") or host_header)
            out["settings"]["servers"][0]["plugin"] = "v2ray-plugin"
            out["settings"]["servers"][0]["pluginOpts"] = opts
        return out

    if scheme == "vmess":
        stream = _tls_stream(params, transport if transport in ("ws", "httpupgrade", "grpc", "tcp") else "tcp")
        if transport in ("ws", "httpupgrade"):
            stream["wsSettings"] = _ws_settings(params, transport)
            if transport == "httpupgrade":
                stream["network"] = "httpupgrade"
        security = stream.get("security") or "none"
        stream = {**stream}
        return {
            "tag": tag,
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": str(params["host"]),
                    "port": int(params["port"]),
                    "users": [{
                        "id": str(params.get("uuid") or ""),
                        "security": "auto",
                        "alterId": 0,
                        "level": 0,
                    }],
                }]
            },
            "streamSettings": stream,
        }

    if scheme in ("vless", "trojan"):
        if transport == "httpupgrade":
            network = "httpupgrade"
        elif transport in ("ws", "xhttp", "grpc", "tcp"):
            network = {"xhttp": "xhttp", "grpc": "grpc", "tcp": "tcp"}.get(transport, "ws")
        else:
            network = "tcp"
        stream = _tls_stream(params, network)
        if network in ("ws", "httpupgrade"):
            stream[f"{network}Settings" if network != "ws" else "wsSettings"] = _ws_settings(params, network)
        if network == "xhttp":
            stream["xhttpSettings"] = {
                "path": str(params.get("path") or "/"),
                "mode": str(params.get("mode") or "stream-one"),
            }
        if network == "grpc":
            stream["grpcSettings"] = {"serviceName": str(params.get("path") or "").strip("/")}
        user: dict[str, Any] = {"level": 0}
        if scheme == "vless":
            user["id"] = str(params.get("uuid") or "")
            user["encryption"] = "none"
        else:
            user["password"] = str(params.get("password") or "")
            # trojan is always TLS on the wire; a link that says otherwise is
            # broken, not exotic.
            if stream.get("security") in (None, "none"):
                stream["security"] = "tls"
                stream["tlsSettings"] = {
                    "serverName": str(params.get("sni") or params["host"]),
                    "allowInsecure": True,
                    "fingerprint": "chrome",
                }
        return {
            "tag": tag,
            "protocol": scheme,
            "settings": {"vnext": [{
                "address": str(params["host"]),
                "port": int(params["port"]),
                "users": [user],
            }]},
            "streamSettings": stream,
        }

    raise ValueError(f"cannot build an xray outbound for {scheme}")


def chain_config(
    outbounds: list[dict],
    *,
    listen_port: int,
    first_hop_direct: bool = True,
) -> dict:
    """Assemble a runnable config: socks inbound -> the outbounds in order.

    Every outbound after the first hangs off the previous one through
    ``proxySettings`` - that is Xray's chaining primitive: the traffic of
    outbound N travels *inside* the tunnel of outbound N-1, so the exit the
    world sees belongs to the last hop. The first hop dials straight from the
    client. ``freedom`` closes the chain so routing has a terminal.
    """
    wired: list[dict] = []
    previous: Optional[str] = None
    for index, outbound in enumerate(outbounds):
        item = dict(outbound)
        if previous is not None:
            item["proxySettings"] = {"tag": previous, "transportLayer": True}
        wired.append(item)
        previous = str(outbound.get("tag"))
    wired.append({"tag": "direct", "protocol": "freedom"})
    return {
        "log": {"loglevel": "info"},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": int(listen_port),
            "protocol": "socks",
            "settings": {"udp": False},
        }],
        "outbounds": wired,
        "routing": {"rules": []},
    }


# --------------------------------------------------------------------- #
# run a config and measure through it
# --------------------------------------------------------------------- #

async def _socks5_echo(port: int, timeout: float) -> tuple[float, str, str]:
    """Dial the local socks inbound and pull the exit address through it."""
    from . import pingtest as pt

    reader, writer = await asyncio.open_connection("127.0.0.1", int(port))
    started = __import__("time").perf_counter()
    try:
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        choice = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        if choice[0] != 5 or choice[1] != 0:
            raise ConnectionResetError("local socks inbound refused")
        domain = pt.ECHO_HOST.encode("idna")
        writer.write(
            b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain
            + struct.pack(">H", pt.ECHO_PORT)
        )
        await writer.drain()
        reply = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        if reply[1] != 0:
            raise ConnectionResetError(f"socks connect failed {reply[1]}")
        if reply[3] == 1:
            await reader.readexactly(4)
        elif reply[3] == 4:
            await reader.readexactly(16)
        else:
            n = (await reader.readexactly(1))[0]
            await reader.readexactly(n)
        await reader.readexactly(2)
        writer.write(pt._echo_payload())
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(8192), timeout=timeout)
        if not raw:
            raise asyncio.TimeoutError("no answer through the core")
        from .pingtest import _split_http_response, _parse_exit

        latency = (__import__("time").perf_counter() - started) * 1000
        status, body = _split_http_response(raw)
        if status != 200:
            raise ConnectionResetError(f"destination answered {status}")
        exit_ip, exit_country = _parse_exit(body)
        return latency, exit_ip, exit_country
    finally:
        await pt._shutdown(writer)


async def run_config(config: dict, *, timeout: float = 15.0) -> tuple[float, str, str]:
    """Run one config through the core and measure the exit through it."""
    binary = find_binary()
    if not binary:
        raise RuntimeError("xray binary not available")
    port = secrets.randbelow(20000) + 40000
    config = dict(config)
    config["inbounds"] = [{
        "listen": "127.0.0.1",
        "port": port,
        "protocol": "socks",
        "settings": {"udp": False},
    }]
    import json as _json
    import tempfile

    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".json", prefix="avtest-", delete=False, dir="/tmp"
    )
    log_path = tmp.name + ".log"
    try:
        tmp.write(_json.dumps(config))
        tmp.close()
        with open(log_path, "wb") as log_file:
            process = await asyncio.create_subprocess_exec(
                binary, "run", "-c", tmp.name,
                stdout=log_file,
                stderr=asyncio.subprocess.DEVNULL,
            )
        try:
            await asyncio.sleep(0.8)  # the core boots in well under this
            return await asyncio.wait_for(_socks5_echo(port, timeout), timeout=timeout)
        except Exception:
            # A refused session is only half an answer; the core's own log says
            # WHY - a 403 from an edge WAF and a timeout are different problems
            # with different fixes.
            detail = ""
            try:
                with open(log_path, "rb") as log_file:
                    detail = log_file.read().decode("utf-8", "ignore")[-400:]
            except Exception:  # noqa: BLE001
                pass
            error = RuntimeError(detail.strip() or "core produced no answer")
            raise error
        finally:
            process.kill()
            try:
                await process.wait()
            except Exception:  # noqa: BLE001
                pass
    finally:
        for path in (tmp.name, log_path):
            try:
                os.unlink(path)
            except OSError:
                pass


async def test_with_core(params: dict, *, timeout: float = 15.0) -> tuple[float, str, str]:
    """Test one parsed link through the real core."""
    outbound = outbound_from_params(params, "probe")
    config = chain_config([outbound], listen_port=0)
    return await run_config(config, timeout=timeout)
