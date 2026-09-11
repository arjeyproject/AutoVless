"""Trojan over WebSocket, on the same worker that already carries VLESS.

Why this exists: a VLESS link and a Trojan link look nothing alike on the wire,
and plenty of Iranian networks that have learned to spot one still pass the
other. The worker sniffs the first frame and speaks whichever protocol arrived,
so a user gets a genuinely different way in without a second panel, a second
account or a second UUID.

Two rules decide what is handed out, and both come from what actually works
rather than from what is merely possible:

  * **TLS only.** Trojan's whole cover story is "this is an ordinary HTTPS
    connection". On a plain port there is no TLS record to hide inside, the
    password crosses the wire in the clear, and v2rayNG, Hiddify and sing-box
    all refuse or break on the result. Plain-port endpoints are filtered out
    here rather than shipped and then blamed on the endpoint.
  * **The password is the panel UUID.** The worker derives the same value when
    ``TROJAN_PASSWORD`` is not bound, so an existing panel starts speaking
    Trojan the moment it picks up a new bundle: no rebuild, no migration, no
    extra binding, nothing new to keep in sync.

The digest a client sends is ``sha224(password)`` in hex. Nothing here computes
it; that is the client's job, and the worker's.
"""

from __future__ import annotations

import base64
import json
from typing import Optional
from urllib.parse import quote, urlencode

from .config import settings
from .vless import WS_PATH, is_tls


def password_for(uuid: str) -> str:
    """The Trojan password for a panel. The value the worker defaults to."""
    return str(uuid)


def usable(endpoints: list[dict]) -> list[dict]:
    """Only the endpoints Trojan can honestly be offered on."""
    return [row for row in endpoints if is_tls(int(row["port"]))]


def remark(endpoint: dict, index: int, brand: str = "") -> str:
    brand = brand or settings.brand
    badge = "\U0001f300" if endpoint.get("kind") == "domain" else "\U0001f3af"
    ping = f"{round(float(endpoint.get('latency') or 0))}ms" if endpoint.get("latency") else "auto"
    port = int(endpoint["port"])
    lock = f" | \U0001f512{port}" if port != 443 else ""
    return (
        f"@{brand} | {badge} TROJAN | \U0001f30d GLOBAL | {ping} | "
        f"{endpoint.get('colo') or 'CF'}{lock} | #{index}"
    )


def build_link(uuid: str, host: str, endpoint: dict, index: int, brand: str = "") -> str:
    params = {
        "security": "tls",
        "type": "ws",
        "host": host,
        "path": WS_PATH,
        "sni": host,
        "fp": "chrome",
        "alpn": "http/1.1",
    }
    query = urlencode(params, quote_via=quote, safe="")
    label = quote(remark(endpoint, index, brand), safe="")
    secret = quote(password_for(uuid), safe="")
    return f"trojan://{secret}@{endpoint['ip']}:{endpoint['port']}?{query}#{label}"


def build_links(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> list[str]:
    rows = usable(endpoints)
    return [build_link(uuid, host, row, index + 1, brand) for index, row in enumerate(rows)]


def build_subscription(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    payload = "\n".join(build_links(uuid, host, endpoints, brand))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def sub_url(uuid: str, host: str) -> str:
    """The worker serves a Trojan-only subscription of its own."""
    return f"https://{host}/{uuid}/trojan"


def build_clash(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    brand = brand or settings.brand
    rows = usable(endpoints)
    secret = password_for(uuid)
    proxies: list[str] = []
    names: list[str] = []

    for index, endpoint in enumerate(rows, start=1):
        name = remark(endpoint, index, brand).replace('"', "'")
        names.append(f'      - "{name}"')
        proxies.append(
            "\n".join(
                [
                    f'  - name: "{name}"',
                    "    type: trojan",
                    f"    server: {endpoint['ip']}",
                    f"    port: {endpoint['port']}",
                    f"    password: {secret}",
                    "    udp: true",
                    f"    sni: {host}",
                    "    client-fingerprint: chrome",
                    "    network: ws",
                    "    ws-opts:",
                    f'      path: "{WS_PATH}"',
                    "      headers:",
                    f"        Host: {host}",
                ]
            )
        )

    return "\n".join(
        [
            f"# {brand} - trojan over websocket, on your own Cloudflare account",
            "mixed-port: 7890",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "proxies:",
            "\n".join(proxies),
            "proxy-groups:",
            f'  - name: "{brand}"',
            "    type: url-test",
            "    url: http://cp.cloudflare.com/generate_204",
            "    interval: 300",
            "    tolerance: 50",
            "    proxies:",
            "\n".join(names),
            "rules:",
            f"  - MATCH,{brand}",
            "",
        ]
    )


def build_singbox(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    secret = password_for(uuid)
    outbounds = []
    for index, endpoint in enumerate(usable(endpoints), start=1):
        outbounds.append(
            {
                "type": "trojan",
                "tag": remark(endpoint, index, brand),
                "server": str(endpoint["ip"]),
                "server_port": int(endpoint["port"]),
                "password": secret,
                "tls": {
                    "enabled": True,
                    "server_name": host,
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                },
                "transport": {
                    "type": "ws",
                    "path": WS_PATH,
                    "headers": {"Host": host},
                    "early_data_header_name": "Sec-WebSocket-Protocol",
                },
            }
        )
    return json.dumps({"outbounds": outbounds}, indent=2, ensure_ascii=False)


def outbound(
    uuid: str,
    host: str,
    endpoint: dict,
    tag: str,
    dialer: Optional[str] = None,
) -> dict:
    """One Xray outbound, optionally dialled through another outbound.

    ``dialer`` is what makes fragmentation work: the ClientHello leaves through
    that outbound, and that is where the packets get cut up.
    """
    stream: dict = {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
            "serverName": host,
            "allowInsecure": False,
            "fingerprint": "chrome",
            "alpn": ["http/1.1"],
        },
        "wsSettings": {"path": WS_PATH, "headers": {"Host": host}},
        "sockopt": {"tcpKeepAliveIdle": 100, "tcpNoDelay": True},
    }
    if dialer:
        stream["sockopt"]["dialerProxy"] = dialer
    return {
        "tag": tag,
        "protocol": "trojan",
        "settings": {
            "servers": [
                {
                    "address": str(endpoint["ip"]),
                    "port": int(endpoint["port"]),
                    "password": password_for(uuid),
                }
            ]
        },
        "streamSettings": stream,
    }
