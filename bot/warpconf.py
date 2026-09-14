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

The second iPhone story, and the reason this file changed again
--------------------------------------------------------------
Dropping the obfuscation made the file *load* on iOS. It did not make the tunnel
*carry traffic*, and the report that followed was the harder one: the handshake
completes, the app shows a connected tunnel, and nothing loads.

Two causes, both fixed here.

``AllowedIPs`` used to be ``0.0.0.0/0, ::/0`` unconditionally. A WARP identity
that Cloudflare issued without an IPv6 address - or one rendered for a platform
whose profile leaves IPv6 out - then claims the whole IPv6 internet through an
interface that has no IPv6 address to source from. Android and Windows shrug at
that. The Apple client installs the route anyway, so every dual-stack lookup
races down a black hole first, and on a carrier that answers AAAA before A that
is every connection the user makes. The route is now claimed only when the
interface actually holds an address in that family.

``Endpoint`` used to be whichever address the pool ranked first, on whatever port
it was measured on. The WARP pool legitimately holds endpoints on a dozen ports,
and the ones the official client never uses are exactly the ones Iranian mobile
carriers drop - a Worker-side scan cannot see that, because the scan does not run
over the carrier. So the Apple platforms now prefer the four ports the official
client itself dials, in its own order, and fall back to the measured ranking only
when the pool has none of them. This is a preference, never a filter: a user
whose pool holds nothing else still gets a file.
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

# The ports the official WARP client dials, in its own order. Preferred on the
# Apple platforms for the reason in the module header: an exotic-but-fast port is
# worse than a boring one that the carrier does not drop.
CLIENT_PORTS: tuple[int, ...] = (2408, 500, 4500, 1701)

PREFERRED_PORTS: Dict[str, tuple[int, ...]] = {
    "ios": CLIENT_PORTS,
    "macos": CLIENT_PORTS,
}


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


def preferred_ports(platform: object = "") -> tuple[int, ...]:
    """Ports this platform's client is known to be happy on, best first."""
    return PREFERRED_PORTS.get(normalise_platform(platform), ())


def order_for(endpoints: Sequence[dict], platform: object = "") -> list[dict]:
    """The endpoint list as this platform should see it.

    Only reorders, never drops: a user who picked Irancell and therefore has an
    IPv6-only pool still gets a working file. IPv4 simply goes first for the
    platforms whose client is happier with it, and on the Apple platforms the
    ports the official client dials come before the ones it never touches.
    """
    rows = [row for row in endpoints if row and row.get("ip")]
    if not rows:
        return rows

    wanted = preferred_ports(platform)
    if wanted:
        rank = {port: index for index, port in enumerate(wanted)}
        # Stable, so the pool's own latency ranking still decides ties.
        rows = sorted(rows, key=lambda row: rank.get(int(row.get("port") or 0), len(wanted)))

    if not prefers_ipv4(platform):
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


def allowed_ips(identity: dict, platform: object = "") -> list[str]:
    """Route only the families the interface can actually source from.

    See the module header: an ``::/0`` catch-all on an interface with no IPv6
    address is what makes an iPhone report a connected tunnel that carries
    nothing.
    """
    rows = addresses(identity, platform)
    has_v4 = any(not is_v6(item.split("/")[0]) for item in rows)
    has_v6 = any(is_v6(item.split("/")[0]) for item in rows)
    out: list[str] = []
    if has_v4 or not has_v6:
        out.append("0.0.0.0/0")
    if has_v6:
        out.append("::/0")
    return out


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
        f"AllowedIPs = {', '.join(allowed_ips(identity, name))}",
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

    if allowed_ips:
        routes = list(allowed_ips)
    else:
        families = {"v6" if is_v6(str(item).split("/")[0]) else "v4" for item in interface_addrs}
        routes = ["0.0.0.0/0"] if "v4" in families or not families else []
        if "v6" in families:
            routes.append("::/0")
        routes = routes or ["0.0.0.0/0"]

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {peer_pubkey}",
        f"AllowedIPs = {', '.join(routes)}",
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
    "CLIENT_PORTS",
    "FALLBACK_ENDPOINTS",
    "PREFERRED_PORTS",
    "addresses",
    "allowed_ips",
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
    "preferred_ports",
    "render",
    "render_amneziawg_warp_config",
    "render_wg_config",
]
