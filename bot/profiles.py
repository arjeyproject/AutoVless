"""Complete client profiles: every protocol the panel speaks, in one file.

Why these live apart from the per-protocol modules
--------------------------------------------------
``bot.vless``, ``bot.trojan`` and ``bot.shadowsocks`` each know how to render
their own links and their own client blocks, and each ships a single-protocol
Clash or sing-box file. That is right for a user who wants one thing. It is wrong
for the common case, which is a user who wants one file that holds everything and
picks whichever entry is alive tonight. Composing that belongs in neither of the
three modules, so it is here.

Two profiles are new, and both exist for a measured reason:

``clash`` / ``singbox``
    All three inbounds in one file, behind a latency test. A group that holds a
    VLESS entry, a Trojan entry and a Shadowsocks entry on the same address is
    the whole point of running three protocols on one worker: when a network
    learns to kill one handshake, the client fails over to a different shape
    without the user touching anything.

``xray_noise``
    Fragmentation plus UDP noise. ``bot.fragment`` already cuts the TLS hello,
    which answers SNI-based blocking. It does nothing for the other half of the
    problem on Iranian mobile: a first UDP burst that gets a session
    flow-classified before any TLS record exists. Xray's ``noises`` prepends
    throwaway packets so the classifier scores the noise instead of the tunnel.
    Kept as a separate profile rather than folded into the fragment export, so a
    client too old to understand ``noises`` still has a file that loads.
"""

from __future__ import annotations

import json
from typing import Sequence

from . import fragment, shadowsocks, trojan, vless
from .config import settings

PROBE_URL = "http://cp.cloudflare.com/generate_204"
NOISE = [
    {"type": "rand", "packet": "10-20", "delay": "10-16"},
    {"type": "rand", "packet": "40-60", "delay": "10-16"},
]


# --------------------------------------------------------------------- #
# clash / mihomo
# --------------------------------------------------------------------- #


def clash(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> str:
    """One Clash file, three protocols, a latency group and a fallback group."""
    brand = brand or settings.brand
    rows = list(endpoints)

    blocks: list[str] = []
    names: list[str] = []

    for index, endpoint in enumerate(rows, start=1):
        secure = vless.is_tls(int(endpoint["port"]))
        name = vless.remark(endpoint, index, brand).replace('"', "'")
        names.append(name)
        lines = [
            f'  - name: "{name}"',
            "    type: vless",
            f"    server: {endpoint['ip']}",
            f"    port: {endpoint['port']}",
            f"    uuid: {uuid}",
            "    udp: true",
            f"    tls: {'true' if secure else 'false'}",
        ]
        if secure:
            lines += [f"    servername: {host}", "    client-fingerprint: chrome"]
        lines += [
            "    network: ws",
            "    ws-opts:",
            f'      path: "{vless.WS_PATH}"',
            "      headers:",
            f"        Host: {host}",
        ]
        blocks.append("\n".join(lines))

    for index, endpoint in enumerate(trojan.usable(rows), start=1):
        name = trojan.remark(endpoint, index, brand).replace('"', "'")
        names.append(name)
        blocks.append(
            "\n".join(
                [
                    f'  - name: "{name}"',
                    "    type: trojan",
                    f"    server: {endpoint['ip']}",
                    f"    port: {endpoint['port']}",
                    f"    password: {trojan.password_for(uuid)}",
                    "    udp: true",
                    f"    sni: {host}",
                    "    client-fingerprint: chrome",
                    "    network: ws",
                    "    ws-opts:",
                    f'      path: "{vless.WS_PATH}"',
                    "      headers:",
                    f"        Host: {host}",
                ]
            )
        )

    if shadowsocks.enabled():
        blocks += shadowsocks.clash_proxies(uuid, host, rows, brand)
        names += shadowsocks.names(uuid, host, rows, brand)

    if not blocks:
        return f"# {brand}: no endpoint is currently verified\nproxies: []\n"

    listed = "\n".join(f'      - "{name}"' for name in names)
    return "\n".join(
        [
            f"# {brand} \u00b7 vless + trojan + shadowsocks",
            "mixed-port: 7890",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "ipv6: false",
            "proxies:",
            "\n".join(blocks),
            "proxy-groups:",
            f'  - name: "{brand}"',
            "    type: url-test",
            f"    url: {PROBE_URL}",
            "    interval: 180",
            "    tolerance: 60",
            "    proxies:",
            listed,
            f'  - name: "{brand} \u00b7 backup"',
            "    type: fallback",
            f"    url: {PROBE_URL}",
            "    interval: 180",
            "    proxies:",
            listed,
            "rules:",
            f"  - MATCH,{brand}",
            "",
        ]
    )


# --------------------------------------------------------------------- #
# sing-box
# --------------------------------------------------------------------- #


def singbox(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> str:
    """A sing-box profile with every protocol behind one urltest.

    Deliberately conservative about schema: a mixed inbound, plain outbounds and
    a urltest. Nothing here moved between sing-box 1.8 and 1.12, which matters
    because the clients people actually have installed span all of it.
    """
    brand = brand or settings.brand
    rows = list(endpoints)

    outbounds: list[dict] = json.loads(vless.build_singbox(uuid, host, rows, brand))["outbounds"]
    outbounds += json.loads(trojan.build_singbox(uuid, host, rows, brand))["outbounds"]
    if shadowsocks.enabled():
        outbounds += shadowsocks.singbox_outbounds(uuid, host, rows, brand)

    tags = [str(item["tag"]) for item in outbounds]
    if not tags:
        return json.dumps({"outbounds": [{"type": "direct", "tag": "direct"}]}, indent=2)

    profile = {
        "log": {"level": "warn", "timestamp": False},
        "dns": {
            "servers": [
                {"tag": "remote", "address": "https://1.1.1.1/dns-query", "detour": brand},
                {"tag": "local", "address": "1.1.1.1", "detour": "direct"},
            ],
            "rules": [{"outbound": "any", "server": "local"}],
            "final": "remote",
            "strategy": "ipv4_only",
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080,
                "sniff": True,
                "sniff_override_destination": False,
            }
        ],
        "outbounds": outbounds
        + [
            {"type": "urltest", "tag": brand, "outbounds": tags, "url": PROBE_URL,
             "interval": "3m", "tolerance": 60},
            {"type": "selector", "tag": "select", "outbounds": [brand] + tags, "default": brand},
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "rules": [{"port": 53, "outbound": "select"}],
            "final": "select",
            "auto_detect_interface": True,
        },
        "experimental": {
            "cache_file": {"enabled": True, "store_fakeip": False},
            "clash_api": {"external_controller": "127.0.0.1:9090"},
        },
    }
    return json.dumps(profile, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------- #
# xray: fragment plus udp noise
# --------------------------------------------------------------------- #


def xray_noise(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> str:
    """The fragment profile, with noise on the dialers as well.

    Built on top of ``bot.fragment`` rather than beside it, so the two cannot
    drift: the outbounds, the balancer and the observatory are the proven ones
    and only the freedom dialers gain a ``noises`` list.
    """
    brand = brand or settings.brand
    config = json.loads(fragment.xray_config(uuid, host, list(endpoints), brand))
    config["remarks"] = f"{brand} \u00b7 Fragment + Noise"
    for item in config.get("outbounds", []):
        if item.get("protocol") == "freedom" and item.get("tag", "").startswith("fragment"):
            item["settings"]["noises"] = [dict(row) for row in NOISE]
    return json.dumps(config, indent=2, ensure_ascii=False)


def filename(kind: str, brand: str = "") -> str:
    slug = (brand or settings.brand).lower().replace(" ", "-")
    suffix = {"clash": "yaml", "singbox": "json", "noise": "json"}.get(kind, "txt")
    return f"{slug}-{kind}.{suffix}"


__all__ = ["clash", "filename", "singbox", "xray_noise"]
