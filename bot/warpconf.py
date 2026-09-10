"""WARP config rendering. One renderer, correct for every client we ship to.

Why this module exists
----------------------
Every export used to build its own INI by hand, and they disagreed on the three
things that decide whether a file even loads:

  * whether an IPv6 endpoint is bracketed - ``[2606:4700:d0::a29f:c001]:2408``
    is valid WireGuard syntax and ``2606:4700:d0::a29f:c001:2408`` is a parse
    error waiting to happen
  * whether the AmneziaWG obfuscation keys appear inside ``[Interface]``
  * MTU, DNS and keepalive per platform

The second one is the whole iPhone story, and it is worth stating plainly because
it was diagnosed as filtering for months: the official WireGuard app for iOS is a
strict INI parser. It meets ``Jc`` inside ``[Interface]``, concludes the file is
not a WireGuard config, and refuses the entire thing. Since every config the bot
handed out was AmneziaWG, every iPhone user got "nothing happens" and blamed the
endpoint. iOS therefore gets clean, standard WireGuard - and because that is a
real downgrade in obfuscation, the delivery message says so out loud.

Why the function names look historical
-------------------------------------
``amnezia_conf``, ``plain_conf``, ``filename`` and ``label`` are the API the
delivery handlers call. They lived here, were dropped in a refactor that
introduced ``render_wg_config``, and ``handlers/pool.py`` went on calling them.
The result was an ``AttributeError`` raised inside the delivery path, *after* the
"building your config" notice had already been sent: the user watched a message
that never turned into a file, which is exactly the bug report we had. They are
back, and the newer ``render_*`` helpers are kept as thin wrappers so nothing
else breaks.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, List, Optional, Sequence

from .config import settings
from .platforms import (
    PlatformProfile,
    default_platform,
    normalise_platform,
    prefers_ipv4,
    profile as platform_profile,
    should_include_amnezia_keys,
)

log = logging.getLogger("autovless.warpconf")

# Emitted in this order. Some AmneziaWG builds are picky about it.
AMNEZIA_KEYS: tuple[str, ...] = (
    "Jc",
    "Jmin",
    "Jmax",
    "S1",
    "S2",
    "S3",
    "S4",
    "H1",
    "H2",
    "H3",
    "H4",
    "I1",
)

# Header magic and packet prefixes stay at WireGuard defaults on purpose: the far
# end of a WARP tunnel is Cloudflare's own unmodified responder and it silently
# drops anything it cannot parse. Only the pre-handshake junk train is safe, so
# S1/S2 stay at zero and H1-H4 keep their standard values.
AMNEZIA_HEADERS: Dict[str, int] = {"S1": 0, "S2": 0, "H1": 1, "H2": 2, "H3": 3, "H4": 4}

# Used only when the pool has nothing at all. These are the addresses the
# official client itself falls back to.
FALLBACK_ENDPOINTS: tuple[tuple[str, int], ...] = (
    ("162.159.192.1", 2408),
    ("162.159.195.1", 500),
    ("188.114.96.1", 1701),
    ("188.114.98.1", 4500),
)


# --------------------------------------------------------------------- #
# addresses and endpoints
# --------------------------------------------------------------------- #


def is_v6(host: object) -> bool:
    return ":" in str(host or "")


def host_port(ip: object, port: object) -> str:
    """``[v6]:port`` or ``v4:port``. WireGuard needs the brackets."""
    text = str(ip)
    try:
        number = int(port)
    except (TypeError, ValueError):
        number = 0
    return f"[{text}]:{number}" if is_v6(text) else f"{text}:{number}"


def bracket_ipv6_endpoint(endpoint: str) -> str:
    """Bracket an ``host:port`` string when the host is IPv6.

    Idempotent, and it leaves hostnames and IPv4 alone. The bug this closes: an
    unbracketed ``2606:4700:d0::a29f:c001:2408`` where the final colon is
    ambiguous, which some clients read as a port and others as part of the
    address.
    """
    text = str(endpoint or "").strip()
    if not text or ":" not in text:
        return text
    if text.startswith("["):
        return text

    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        try:
            ipaddress.IPv6Address(text)
        except ValueError:
            return text
        return f"[{text}]"

    try:
        if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
            return f"[{host}]:{port}"
    except ValueError:
        pass
    return text


def order_for(endpoints: Sequence[dict], platform: object = "") -> list[dict]:
    """The endpoint list as this platform should see it.

    Only reorders, never drops: a user who picked Irancell and therefore has an
    IPv6-only pool still gets a working file. IPv4 simply goes first for the
    platforms whose client is happier with it.
    """
    rows = [row for row in endpoints if row and row.get("ip")]
    if not rows or not prefers_ipv4(platform):
        return rows
    v4 = [row for row in rows if not is_v6(row["ip"])]
    v6 = [row for row in rows if is_v6(row["ip"])]
    return v4 + v6


def endpoint_of(
    endpoints: Sequence[dict] = (),
    index: int = 0,
    platform: object = "",
) -> tuple[str, int]:
    rows = order_for(endpoints, platform)
    if rows:
        chosen = rows[min(max(0, index), len(rows) - 1)]
        return str(chosen["ip"]), int(chosen["port"])
    fallback = FALLBACK_ENDPOINTS[max(0, index) % len(FALLBACK_ENDPOINTS)]
    return fallback[0], fallback[1]


def label(
    endpoints: Sequence[dict] = (),
    index: int = 0,
    platform: object = "",
) -> str:
    """The endpoint as it will appear in the config, ready to print."""
    host, port = endpoint_of(endpoints, index, platform)
    return host_port(host, port)


def addresses(identity: dict, platform: object = "") -> list[str]:
    out: list[str] = []
    if identity.get("v4"):
        out.append(f"{identity['v4']}/32")
    if identity.get("v6") and platform_profile(platform).supports_ipv6:
        out.append(f"{identity['v6']}/128")
    return out or ["172.16.0.2/32"]


def filename(family: str = "", kind: str = "awg", platform: str = "") -> str:
    """A filename a user can tell apart in their downloads folder."""
    brand = (settings.brand or "autovless").strip().lower().replace(" ", "-")
    parts = [brand or "autovless", "warp"]
    if family:
        parts.append(str(family).strip().lower())
    if platform:
        parts.append(normalise_platform(platform))
    kind = (kind or "awg").strip().lower()
    if kind not in {"awg", "conf"}:
        parts.append(kind)
    stem = "-".join(part for part in parts if part)
    if kind == "singbox":
        return f"{stem}.json"
    if kind == "clash":
        return f"{stem}.yaml"
    return f"{stem}.conf"


# --------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------- #


def _dns_line(prof: PlatformProfile, dns: Optional[object]) -> str:
    if isinstance(dns, (list, tuple)):
        servers = [str(item).strip() for item in dns if str(item).strip()]
    elif dns:
        servers = [part.strip() for part in str(dns).split(",") if part.strip()]
    else:
        servers = [part.strip() for part in str(settings.warp_dns).split(",") if part.strip()]
    return ", ".join(servers or prof.dns_servers)


def _mtu(prof: PlatformProfile, mtu: Optional[int]) -> int:
    if mtu:
        return int(mtu)
    # The configured value keeps the operator's knob, but never above what the
    # platform can actually carry.
    configured = int(settings.warp_mtu or 0)
    return min(configured, prof.mtu) if configured else prof.mtu


def _junk(values: Optional[dict]) -> Dict[str, Any]:
    """Turn an obfuscation profile into the keys AmneziaWG expects."""
    out: Dict[str, Any] = dict(AMNEZIA_HEADERS)
    source = values or {}
    for key, name in (("jc", "Jc"), ("jmin", "Jmin"), ("jmax", "Jmax")):
        if source.get(key) is not None:
            out[name] = source[key]
    return out


def render(
    identity: dict,
    endpoints: Sequence[dict] = (),
    platform: object = "",
    obfuscation: Optional[dict] = None,
    mtu: Optional[int] = None,
    dns: Optional[object] = None,
    signature: bool = False,
    index: int = 0,
    force_clean: bool = False,
) -> str:
    """The one renderer. Everything else here is a thin wrapper over it.

    ``force_clean`` drops the obfuscation even on a platform that supports it,
    which is what the plain WireGuard export button asks for.
    """
    name = normalise_platform(platform)
    prof = platform_profile(name)
    host, port = endpoint_of(endpoints, index, name)

    obfuscated = (
        not force_clean and bool(settings.warp_amnezia) and should_include_amnezia_keys(name)
    )

    interface = [
        "[Interface]",
        f"PrivateKey = {identity['private_key']}",
        f"Address = {', '.join(addresses(identity, name))}",
        f"DNS = {_dns_line(prof, dns)}",
        f"MTU = {_mtu(prof, mtu)}",
    ]

    if obfuscated:
        values = _junk(obfuscation)
        if signature and (obfuscation or {}).get("i1"):
            values["I1"] = (obfuscation or {})["i1"]
        for key in AMNEZIA_KEYS:
            if key in values:
                interface.append(f"{key} = {values[key]}")

    peer = [
        "",
        "[Peer]",
        f"PublicKey = {identity['peer_public_key']}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        f"Endpoint = {bracket_ipv6_endpoint(host_port(host, port))}",
    ]
    if prof.keepalive:
        peer.append(f"PersistentKeepalive = {int(prof.keepalive)}")
    peer.append("")

    return "\n".join(interface + peer)


def amnezia_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    profile: Optional[dict] = None,
    mtu: Optional[int] = None,
    dns: Optional[object] = None,
    signature: bool = False,
    platform: object = "",
    index: int = 0,
) -> str:
    """AmneziaWG, unless the platform cannot take it - then clean WireGuard.

    The signature is deliberately the one the delivery handlers were already
    calling with, so restoring this function fixes the path without either of
    them changing shape.
    """
    return render(
        identity,
        endpoints,
        platform=platform or default_platform(),
        obfuscation=profile,
        mtu=mtu,
        dns=dns,
        signature=signature,
        index=index,
    )


def plain_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    mtu: Optional[int] = None,
    dns: Optional[object] = None,
    platform: object = "",
    index: int = 0,
) -> str:
    """Standard WireGuard, no obfuscation anywhere. What iOS actually accepts."""
    return render(
        identity,
        endpoints,
        platform=platform or "ios",
        mtu=mtu,
        dns=dns,
        index=index,
        force_clean=True,
    )


def conf_for(
    identity: dict,
    endpoints: Sequence[dict] = (),
    platform: object = "",
    kind: str = "",
    profile: Optional[dict] = None,
    index: int = 0,
) -> str:
    """Render whichever flavour this platform and export kind imply."""
    name = normalise_platform(platform)
    kind = (kind or "").strip().lower()
    if kind == "plain" or not should_include_amnezia_keys(name):
        return plain_conf(identity, endpoints, platform=name, index=index)
    return amnezia_conf(
        identity,
        endpoints,
        profile,
        signature=kind == "awg2",
        platform=name,
        index=index,
    )


def is_clean_for(platform: object) -> bool:
    """True when this platform is handed a config with no obfuscation in it.

    The delivery message reads this. Telling an iPhone user their junk train is
    ``Jc=6`` when the file deliberately has none would be a lie on the screen.
    """
    return not should_include_amnezia_keys(platform)


# --------------------------------------------------------------------- #
# back-compatible wrappers
# --------------------------------------------------------------------- #


def render_wg_config(
    interface_privkey: str,
    interface_addrs: List[str],
    peer_pubkey: str,
    peer_endpoint: str,
    allowed_ips: Optional[List[str]] = None,
    dns_servers: Optional[List[str]] = None,
    platform: str = "android",
    amnezia_keys: Optional[Dict[str, Any]] = None,
    mtu: Optional[int] = None,
) -> str:
    """Kept for callers that pass raw pieces rather than an identity dict."""
    prof = platform_profile(platform)
    lines = ["[Interface]", f"PrivateKey = {interface_privkey}"]
    if interface_addrs:
        lines.append(f"Address = {', '.join(interface_addrs)}")
    lines.append(f"DNS = {_dns_line(prof, dns_servers)}")
    lines.append(f"MTU = {_mtu(prof, mtu)}")
    if should_include_amnezia_keys(platform) and amnezia_keys:
        for key in AMNEZIA_KEYS:
            if key in amnezia_keys:
                lines.append(f"{key} = {amnezia_keys[key]}")

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {peer_pubkey}",
        f"AllowedIPs = {', '.join(allowed_ips or ['0.0.0.0/0', '::/0'])}",
        f"Endpoint = {bracket_ipv6_endpoint(peer_endpoint)}",
    ]
    if prof.keepalive:
        lines.append(f"PersistentKeepalive = {int(prof.keepalive)}")
    lines.append("")
    return "\n".join(lines)


def render_amneziawg_warp_config(
    interface_privkey: str,
    interface_addr4: str,
    interface_addr6: str,
    peer_pubkey: str,
    peer_endpoint: str,
    platform: str = "android",
    use_custom_dns: bool = True,
    custom_dns: Optional[List[str]] = None,
    mtu: Optional[int] = None,
    **amnezia_params: Any,
) -> str:
    """Kept for the same reason as ``render_wg_config``."""
    addrs = [addr for addr in (interface_addr4, interface_addr6) if addr]
    if not platform_profile(platform).supports_ipv6:
        addrs = [addr for addr in addrs if not is_v6(addr.split("/")[0])]
    return render_wg_config(
        interface_privkey,
        addrs,
        peer_pubkey,
        peer_endpoint,
        dns_servers=custom_dns if use_custom_dns else [],
        platform=platform,
        amnezia_keys={
            key: value for key, value in amnezia_params.items() if key in AMNEZIA_KEYS
        },
        mtu=mtu,
    )


__all__ = [
    "AMNEZIA_HEADERS",
    "AMNEZIA_KEYS",
    "FALLBACK_ENDPOINTS",
    "addresses",
    "amnezia_conf",
    "bracket_ipv6_endpoint",
    "conf_for",
    "endpoint_of",
    "filename",
    "host_port",
    "is_clean_for",
    "is_v6",
    "label",
    "order_for",
    "plain_conf",
    "render",
    "render_amneziawg_warp_config",
    "render_wg_config",
]
