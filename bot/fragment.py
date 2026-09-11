"""One button, one file: every config the user owns, fragmented.

What fragmentation is for
-------------------------
The block that hurts most is not an IP block. It is DPI reading the TLS
ClientHello, finding the SNI, and killing the connection before the handshake
finishes. Xray's ``fragment`` outbound cuts that first record into small pieces
sent milliseconds apart, so the inspector never sees one contiguous hello to
match on. Same endpoint, same UUID, same worker: only the shape of the first few
packets changes, and a config that died on handshake starts connecting.

Why this is a generated file and not a switch in the link
---------------------------------------------------------
Fragmentation lives in the client, not the server, and it is configured on the
*dialer*. There is no query parameter for it that every client agrees on, so a
``vless://`` link cannot carry it. A full Xray JSON can, and v2rayNG, Streisand,
V2Box and Hiddify all import one. So the bot renders every endpoint the user
holds into a single JSON, each proxy dialled through a fragment outbound, with a
least-ping balancer on top so the client keeps using whichever one is alive.

Two fragment outbounds, on purpose
----------------------------------
``fragment`` cuts the TLS hello and is what the port 443 configs use.
``fragment-raw`` cuts the first few raw packets instead, because a plain-port
config has no TLS record to slice and ``tlshello`` would be a no-op on it. Every
config in the file therefore gets fragmentation that means something for the way
it actually connects.
"""

from __future__ import annotations

import json
from typing import Optional

from . import trojan as trojan_mod
from .config import settings
from .vless import WS_PATH, is_tls

# Fragment tuning. These are the values that hold up on Iranian mobile networks:
# small enough to break the hello apart, slow enough that the pieces are not
# reassembled by the first hop, fast enough that the handshake still completes
# inside a client's patience.
TLS_FRAGMENT = {"packets": "tlshello", "length": "100-200", "interval": "10-20"}
RAW_FRAGMENT = {"packets": "1-3", "length": "100-200", "interval": "10-20"}

SOCKS_PORT = 10808
HTTP_PORT = 10809
PROBE_URL = "https://www.gstatic.com/generate_204"


def _sockopt(dialer: str) -> dict:
    return {"dialerProxy": dialer, "tcpKeepAliveIdle": 100, "tcpNoDelay": True}


def _vless_outbound(uuid: str, host: str, endpoint: dict, tag: str, dialer: str) -> dict:
    secure = is_tls(int(endpoint["port"]))
    stream: dict = {
        "network": "ws",
        "security": "tls" if secure else "none",
        "wsSettings": {"path": WS_PATH, "headers": {"Host": host}},
        "sockopt": _sockopt(dialer),
    }
    if secure:
        stream["tlsSettings"] = {
            "serverName": host,
            "allowInsecure": False,
            "fingerprint": "chrome",
            "alpn": ["http/1.1"],
        }
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": str(endpoint["ip"]),
                    "port": int(endpoint["port"]),
                    "users": [{"id": uuid, "encryption": "none", "level": 8, "flow": ""}],
                }
            ]
        },
        "streamSettings": stream,
    }


def _trojan_outbound(uuid: str, host: str, endpoint: dict, tag: str, dialer: str) -> dict:
    item = trojan_mod.outbound(uuid, host, endpoint, tag)
    item["streamSettings"]["sockopt"] = _sockopt(dialer)
    return item


def _dialer(endpoint: dict) -> str:
    return "fragment" if is_tls(int(endpoint["port"])) else "fragment-raw"


def outbounds(
    uuid: str,
    host: str,
    endpoints: list[dict],
    with_trojan: bool = True,
) -> list[dict]:
    """Every config the user holds, as fragmented Xray outbounds.

    The first one is tagged ``proxy`` because some clients still look for that
    exact tag; the rest are ``proxy-2`` upwards, which is also the prefix the
    observatory and the balancer select on.
    """
    rows: list[tuple[str, dict]] = [("vless", endpoint) for endpoint in endpoints]
    if with_trojan:
        rows += [("trojan", endpoint) for endpoint in trojan_mod.usable(endpoints)]

    out: list[dict] = []
    for index, (kind, endpoint) in enumerate(rows, start=1):
        tag = "proxy" if index == 1 else f"proxy-{index}"
        dialer = _dialer(endpoint)
        if kind == "trojan":
            out.append(_trojan_outbound(uuid, host, endpoint, tag, dialer))
        else:
            out.append(_vless_outbound(uuid, host, endpoint, tag, dialer))
    return out


def xray_config(
    uuid: str,
    host: str,
    endpoints: list[dict],
    brand: str = "",
    with_trojan: bool = True,
    dns: Optional[list[str]] = None,
) -> str:
    """A complete, importable Xray config with fragmentation on every proxy."""
    brand = brand or settings.brand
    proxies = outbounds(uuid, host, endpoints, with_trojan)

    config = {
        "remarks": f"{brand} \u00b7 Fragment",
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": dns or ["1.1.1.1", "8.8.8.8", "localhost"],
            "queryStrategy": "UseIP",
        },
        "inbounds": [
            {
                "tag": "socks",
                "port": SOCKS_PORT,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True, "auth": "noauth"},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            },
            {
                "tag": "http",
                "port": HTTP_PORT,
                "listen": "127.0.0.1",
                "protocol": "http",
                "settings": {},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            },
        ],
        "outbounds": proxies
        + [
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {"domainStrategy": "AsIs", "fragment": dict(TLS_FRAGMENT)},
                "streamSettings": {"sockopt": {"tcpKeepAliveIdle": 100, "tcpNoDelay": True}},
            },
            {
                "tag": "fragment-raw",
                "protocol": "freedom",
                "settings": {"domainStrategy": "AsIs", "fragment": dict(RAW_FRAGMENT)},
                "streamSettings": {"sockopt": {"tcpKeepAliveIdle": 100, "tcpNoDelay": True}},
            },
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {
                "tag": "block",
                "protocol": "blackhole",
                "settings": {"response": {"type": "http"}},
            },
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "balancers": [
                {"tag": "auto", "selector": ["proxy"], "strategy": {"type": "leastPing"}}
            ],
            "rules": [
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": "direct"},
                {"type": "field", "network": "tcp,udp", "balancerTag": "auto"},
            ],
        },
        # Without this the balancer has no latency to compare and quietly falls
        # back to the first outbound, which defeats the point of listing them all.
        "observatory": {
            "subjectSelector": ["proxy"],
            "probeUrl": PROBE_URL,
            "probeInterval": "30s",
            "enableConcurrency": True,
        },
    }

    if not proxies:
        # A config that names a balancer with no members refuses to start, so an
        # empty pool must not produce one.
        config["routing"]["rules"] = [
            {"type": "field", "network": "tcp,udp", "outboundTag": "direct"}
        ]
        config["routing"].pop("balancers", None)
        config.pop("observatory", None)

    return json.dumps(config, indent=2, ensure_ascii=False)


def filename(brand: str = "") -> str:
    slug = (brand or settings.brand).lower().replace(" ", "-")
    return f"{slug}-fragment.json"
