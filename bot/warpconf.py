"""Config rendering that is correct for both address families.

``bot.warp`` renders configs the way it always has, and it is written for IPv4:
it emits ``Endpoint = host:port``. That is a syntax error the moment ``host`` is
an IPv6 literal, because ``2606:4700:d0::a29f:c001:2408`` is not an address and a
port, it is nine colons and a client that refuses to import the file.

Every format has its own opinion about this:

  * WireGuard and AmneziaWG want ``[v6]:port``
  * a ``wireguard://`` share link wants the host bracketed too, or the URL parser
    swallows the port
  * sing-box and Clash keep server and port in separate fields, so the bare
    address is right and brackets would be wrong

So the rendering lives here, once, and every WARP screen goes through it. The
legacy renderers in ``bot.warp`` are left alone on purpose: they are only ever
handed IPv4 rows (``warpscan._pool`` is pinned to that family) and retyping
working registration code to fix a formatting bug would be a bad trade.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

from . import warp as warpcore
from . import warpep
from .config import settings

# Where AmneziaVPN actually lives, per platform. Used for the short how-to that
# rides along with every config.
AMNEZIA_PLAY = "https://play.google.com/store/apps/details?id=org.amnezia.vpn"
AMNEZIA_APPSTORE = "https://apps.apple.com/us/app/amneziavpn/id1600480750"
AMNEZIA_DESKTOP = "https://github.com/amnezia-vpn/amnezia-client/releases/latest"


def addresses(identity: dict) -> list[str]:
    out: list[str] = []
    if identity.get("v4"):
        out.append(f"{identity['v4']}/32")
    if identity.get("v6"):
        out.append(f"{identity['v6']}/128")
    return out


def endpoint_of(endpoints: Sequence[dict], index: int = 0) -> tuple[str, int]:
    if endpoints:
        chosen = endpoints[min(index, len(endpoints) - 1)]
        return str(chosen["ip"]), int(chosen["port"])
    return warpcore.FALLBACK_ENDPOINTS[index % len(warpcore.FALLBACK_ENDPOINTS)]


def label(endpoints: Sequence[dict], index: int = 0) -> str:
    """``[v6]:port`` or ``v4:port``, ready to print."""
    host, port = endpoint_of(endpoints, index)
    return warpep.host_port(host, port)


def family_of(endpoints: Sequence[dict]) -> str:
    host, _ = endpoint_of(endpoints)
    return warpep.family_of(host)


def _name(family: str, suffix: str) -> str:
    return f"{settings.brand}-warp-{family}{suffix}"


def filename(family: str, kind: str) -> str:
    """A filename that says which pool the config came out of."""
    return _name(family, {"awg": ".conf", "awg2": "-v2.conf", "plain": "-wg.conf"}.get(kind, ".conf"))


def _allowed_ips(identity: dict) -> str:
    """Build AllowedIPs based on what address families the identity actually has.
    
    Only include IPv6 routes if the identity has an IPv6 address, and only IPv4
    if it has IPv4. This fixes clients like iPhone WireGuard that reject configs
    with AllowedIPs that reference unreachable address families.
    """
    allowed = []
    if identity.get("v4"):
        allowed.append("0.0.0.0/0")
    if identity.get("v6"):
        allowed.append("::/0")
    # Fallback: if somehow neither is set, include both (shouldn't happen)
    if not allowed:
        return "0.0.0.0/0, ::/0"
    return ", ".join(allowed)


# --------------------------------------------------------------------- #
# formats
# --------------------------------------------------------------------- #


def wireguard_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    mtu: Optional[int] = None,
    dns: Optional[str] = None,
) -> str:
    """Plain WireGuard. Kept for clients without obfuscation support."""
    host, port = endpoint_of(endpoints)
    return "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {identity['private_key']}",
            f"Address = {', '.join(addresses(identity))}",
            f"DNS = {dns or settings.warp_dns}",
            f"MTU = {mtu or settings.warp_mtu}",
            "",
            "[Peer]",
            f"PublicKey = {identity['peer_public_key']}",
            f"AllowedIPs = {_allowed_ips(identity)}",
            f"Endpoint = {warpep.host_port(host, port)}",
            "PersistentKeepalive = 25",
            "",
        ]
    )


def amnezia_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    profile: Optional[dict] = None,
    mtu: Optional[int] = None,
    dns: Optional[str] = None,
    signature: bool = False,
) -> str:
    """AmneziaWG. ``signature`` adds the I1 decoy, which needs AmneziaWG 1.5+.

    H1-H4 and S1/S2 stay at their WireGuard defaults because the peer on the
    other end is Cloudflare's own unmodified WARP responder: only the junk train
    in front of the handshake is ours to change.
    """
    host, port = endpoint_of(endpoints)
    profile = profile or warpcore.obfuscation(identity.get("private_key", ""))

    lines = [
        "[Interface]",
        f"PrivateKey = {identity['private_key']}",
        f"Address = {', '.join(addresses(identity))}",
        f"DNS = {dns or settings.warp_dns}",
        f"MTU = {mtu or settings.warp_mtu}",
        f"Jc = {profile['jc']}",
        f"Jmin = {profile['jmin']}",
        f"Jmax = {profile['jmax']}",
        "S1 = 0",
        "S2 = 0",
        "H1 = 1",
        "H2 = 2",
        "H3 = 3",
        "H4 = 4",
    ]
    if signature:
        lines.append(f"I1 = {profile['i1']}")
    lines += [
        "",
        "[Peer]",
        f"PublicKey = {identity['peer_public_key']}",
        f"AllowedIPs = {_allowed_ips(identity)}",
        f"Endpoint = {warpep.host_port(host, port)}",
        "PersistentKeepalive = 25",
        "",
    ]
    return "\n".join(lines)


def warp_link(
    identity: dict,
    endpoints: Sequence[dict] = (),
    index: int = 0,
    name: Optional[str] = None,
    mtu: Optional[int] = None,
) -> str:
    """wireguard:// share link for Xray based clients, with UDP noise attached."""
    from urllib.parse import quote

    host, port = endpoint_of(endpoints, index)
    tag = name or f"{settings.brand}-WARP"
    reserved = "%2C".join(str(part) for part in identity.get("reserved") or [0, 0, 0])
    address = "%2C".join(quote(item, safe="") for item in addresses(identity))
    return (
        f"wireguard://{quote(identity['private_key'], safe='')}"
        f"@{warpep.bracket(host)}:{port}"
        f"?address={address}"
        f"&publickey={quote(identity['peer_public_key'], safe='')}"
        f"&reserved={reserved}"
        f"&mtu={mtu or settings.warp_mtu}"
        "&keepalive=25"
        "&wnoise=quic&wnoisecount=15&wpayloadsize=1-1500&wnoisedelay=1-10"
        f"#{quote(tag, safe='')}"
    )


def links(identity: dict, endpoints: Sequence[dict]) -> list[str]:
    total = max(1, len(endpoints)) if endpoints else len(warpcore.FALLBACK_ENDPOINTS)
    return [
        warp_link(identity, endpoints, index, f"{settings.brand}-WARP-{index + 1}")
        for index in range(total)
    ]


def singbox_json(identity: dict, endpoints: Sequence[dict], mtu: Optional[int] = None) -> str:
    """sing-box keeps server and port apart, so the address stays unbracketed."""
    outbounds = []
    total = max(1, len(endpoints)) if endpoints else len(warpcore.FALLBACK_ENDPOINTS)
    for index in range(total):
        host, port = endpoint_of(endpoints, index)
        outbounds.append(
            {
                "type": "wireguard",
                "tag": f"{settings.brand}-WARP-{index + 1}",
                "server": host,
                "server_port": port,
                "local_address": addresses(identity),
                "private_key": identity["private_key"],
                "peer_public_key": identity["peer_public_key"],
                "reserved": identity.get("reserved") or [0, 0, 0],
                "mtu": mtu or settings.warp_mtu,
            }
        )
    return json.dumps({"outbounds": outbounds}, indent=2, ensure_ascii=False)


def clash_yaml(identity: dict, endpoints: Sequence[dict], mtu: Optional[int] = None) -> str:
    total = max(1, len(endpoints)) if endpoints else len(warpcore.FALLBACK_ENDPOINTS)
    reserved = ", ".join(str(part) for part in identity.get("reserved") or [0, 0, 0])
    proxies: list[str] = []
    names: list[str] = []

    for index in range(total):
        host, port = endpoint_of(endpoints, index)
        name = f"{settings.brand}-WARP-{index + 1}"
        names.append(f'      - "{name}"')
        block = [
            f'  - name: "{name}"',
            "    type: wireguard",
            f"    server: {host}",
            f"    port: {port}",
            f"    ip: {identity['v4']}",
        ]
        if identity.get("v6"):
            block.append(f"    ipv6: {identity['v6']}")
        block += [
            f"    private-key: {identity['private_key']}",
            f"    public-key: {identity['peer_public_key']}",
            f"    reserved: [{reserved}]",
            f"    mtu: {mtu or settings.warp_mtu}",
            "    udp: true",
            "    remote-dns-resolve: true",
            f"    dns: [{settings.warp_dns}]",
        ]
        proxies.append("\n".join(block))

    return "\n".join(
        [
            f"# {settings.brand} WARP",
            "mixed-port: 7890",
            "mode: rule",
            "proxies:",
            "\n".join(proxies),
            "proxy-groups:",
            f'  - name: "{settings.brand}-WARP"',
            "    type: url-test",
            "    url: http://cp.cloudflare.com/generate_204",
            "    interval: 300",
            "    proxies:",
            "\n".join(names),
            "rules:",
            f"  - MATCH,{settings.brand}-WARP",
            "",
        ]
    )
