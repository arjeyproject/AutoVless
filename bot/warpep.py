"""WarpEP inside AutoVless: the search space, the verdict, and the deep check.

AutoVless does not guess at WARP addresses and it does not invent its own idea of
"healthy". Both come from WarpEP (https://github.com/arjeyproject/WarpEP), and
this module is the only seam between the two projects:

  * **the search space** - Cloudflare's published WARP anycast prefixes for IPv4
    *and* IPv6, plus the UDP port ladder the official client falls back through.
  * **the verdict** - WarpEP's 0-100 health formula, where loss dominates,
    latency comes second and jitter third. A row below the floor is never stored,
    so the pool can only ever hold endpoints that actually answered.
  * **the identity** - the one thing that decides real results from dead ones.
    Read ``fallback_identity`` below before touching anything in here.
  * **the routes** - whether this host can even reach a family. A container on
    Docker's default bridge has no IPv6 route at all, and without ``reachable``
    the scanner cheerfully reported every IPv6 address as dead.
  * **the deep check** - when the ``warpep`` package is installed an endpoint can
    be proven to *carry traffic* (real ICMP sealed into the tunnel and decrypted
    on the way back), not merely to answer one handshake. That is the difference
    between "it pings" and "it works", and it is the one test that catches the
    dead-but-pinging trap Iranian DPI produces all day long.

If the package is not installed the prefixes, ports and formula come from the
vendored copy below and the deep check reports "not checked" rather than failing
a healthy endpoint. Nothing here ever blocks the event loop: the WarpEP engine is
synchronous, so the deep check runs in a worker thread.

The handshake itself stays with ``bot.wireguard``, which is already a real,
async, cryptographically verified Noise_IK initiation. Two crypto stacks racing
inside one bot would be a bug, not a feature.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import random
import socket
from typing import Optional, Sequence

log = logging.getLogger("autovless.warpep")

V4 = "v4"
V6 = "v6"
FAMILIES: tuple[str, str] = (V4, V6)

# --------------------------------------------------------------------- #
# vendored copy of WarpEP's address space
# --------------------------------------------------------------------- #

_V4_PREFIXES: tuple[str, ...] = (
    "162.159.192.0/24",
    "162.159.193.0/24",
    "162.159.195.0/24",
    "188.114.96.0/24",
    "188.114.97.0/24",
    "188.114.98.0/24",
    "188.114.99.0/24",
)

_V6_PREFIXES: tuple[str, ...] = (
    "2606:4700:d0::/64",
    "2606:4700:d1::/64",
)

# The two interface-id bases Cloudflare hands WARP clients inside those /64s.
_V6_BASES: tuple[int, ...] = (0xA29F, 0xBC72)

_PRIMARY_PORTS: tuple[int, ...] = (2408, 500, 1701, 4500, 8886, 8854, 894, 943)

_EXTENDED_PORTS: tuple[int, ...] = (
    854, 859, 864, 878, 880, 890, 891, 903, 908, 928, 934, 939, 942, 945, 946,
    955, 968, 987, 988, 1002, 1010, 1014, 1018, 1070, 1074, 1180, 1387, 1843,
    2371, 2506, 3138, 3476, 3581, 3854, 4177, 4198, 4233, 5279, 5956, 7103,
    7152, 7156, 7281, 7559, 8319, 8742,
)

# Addresses the official client itself falls back to. If none of these answer the
# fault is local, and no amount of scanning will find anything.
CONTROL: dict[str, tuple[tuple[str, int], ...]] = {
    V4: (
        ("162.159.192.1", 2408),
        ("162.159.193.10", 2408),
        ("188.114.96.1", 2408),
        ("188.114.98.10", 2408),
    ),
    V6: (
        ("2606:4700:d0::a29f:c001", 2408),
        ("2606:4700:d1::a29f:c101", 2408),
    ),
}

# Cloudflare's WARP WireGuard responder public key. Every WARP client on the
# planet handshakes against this exact key and it has not changed since WARP
# shipped, so it is a safe default when a registration payload is unavailable.
RESPONDER_PUBLIC_KEY = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="

# An *enrolled* WARP device key, already published in other open-source WARP
# tools and vendored here from WarpEP's own bundled identity.
#
# Read this before deleting it. Cloudflare's responder checks mac1 (anybody can
# compute that), then decrypts the initiation to learn which client is calling,
# and looks that public key up in its peer list. If the key is not an enrolled
# WARP device the packet is dropped in silence: no response, no ICMP, nothing.
# So an unregistered or revoked identity does not make endpoints look slow, it
# makes every endpoint on earth look dead - which is precisely the "48 scanned,
# 0 answered" the pools were reporting. This key only ever *probes*; it carries
# no user traffic and is tied to nobody's account.
FALLBACK_PRIVATE_KEY = "4OnO86dDLpqJ2U10ODwX3tarx6xlRGLfkmbSBtMgaHg="

# --------------------------------------------------------------------- #
# prefer the installed package
# --------------------------------------------------------------------- #

try:  # pragma: no cover - depends on the deployment
    from warpep import endpoints as _upstream  # type: ignore
    from warpep.version import __version__ as _upstream_version  # type: ignore
except Exception:  # noqa: BLE001 - any import problem means "use the copy"
    _upstream = None
    _upstream_version = ""


def _upstream_tuple(name: str, fallback: tuple) -> tuple:
    """Take a constant from the package, and never die because it was renamed.

    The old code read these attributes unguarded, so a single upstream rename
    would raise ``AttributeError`` at import time and take the whole bot down
    rather than degrading to the vendored copy.
    """
    if _upstream is None:
        return fallback
    try:
        return tuple(getattr(_upstream, name))
    except Exception:  # noqa: BLE001
        log.warning("warpep.%s is missing, using the vendored copy", name)
        return fallback


IPV4_PREFIXES: tuple[str, ...] = _upstream_tuple("IPV4_PREFIXES", _V4_PREFIXES)
IPV6_PREFIXES: tuple[str, ...] = _upstream_tuple("IPV6_PREFIXES", _V6_PREFIXES)
PRIMARY_PORTS: tuple[int, ...] = _upstream_tuple("PRIMARY_PORTS", _PRIMARY_PORTS)
EXTENDED_PORTS: tuple[int, ...] = _upstream_tuple("EXTENDED_PORTS", _EXTENDED_PORTS)
SOURCE = (
    f"warpep {_upstream_version or 'installed'}" if _upstream is not None else "warpep (vendored)"
)

ALL_PORTS: tuple[int, ...] = tuple(dict.fromkeys(PRIMARY_PORTS + EXTENDED_PORTS))


def installed() -> bool:
    """True when the real WarpEP package is importable, so the deep check works."""
    return _upstream is not None


# --------------------------------------------------------------------- #
# families and formatting
# --------------------------------------------------------------------- #


def family_of(ip: str) -> str:
    """``v6`` for an IPv6 literal, ``v4`` for everything else."""
    return V6 if ":" in str(ip) else V4


def normalise_family(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {V6, "6", "ipv6", "inet6"}:
        return V6
    return V4


def prefixes(family: str) -> tuple[str, ...]:
    return IPV6_PREFIXES if normalise_family(family) == V6 else IPV4_PREFIXES


def host_port(ip: str, port: object) -> str:
    """``[v6]:port`` or ``v4:port``. WireGuard configs need the brackets."""
    text = str(ip)
    return f"[{text}]:{int(port)}" if ":" in text else f"{text}:{int(port)}"


def bracket(ip: str) -> str:
    text = str(ip)
    return f"[{text}]" if ":" in text else text


def block_of(ip: str) -> str:
    """Grouping key, so one blackholed block cannot fill a user's whole config."""
    text = str(ip)
    if ":" in text:
        return ":".join(text.split(":")[:4])
    return text.rsplit(".", 1)[0]


# --------------------------------------------------------------------- #
# what this host can actually reach
# --------------------------------------------------------------------- #

# One address per family, used only to ask the kernel for a route.
_ROUTE_PROBE: dict[str, str] = {V4: "162.159.192.1", V6: "2606:4700:d0::a29f:c001"}

_routes: dict[str, Optional[bool]] = {V4: None, V6: None}


def _probe_route(family: str) -> bool:
    """Has the kernel got a route for this family at all?

    ``connect`` on a UDP socket sends no packet, so this costs nothing and takes
    no time. It exists because a container on Docker's default bridge network has
    no IPv6 route whatsoever: every IPv6 probe then fails instantly with
    ``ENETUNREACH``, and the old code counted each of those as a dead endpoint.
    Forty-eight addresses, zero answers, four seconds, and an IPv6 pool that
    could never fill no matter how many times anybody pressed refresh.
    """
    code = normalise_family(family)
    inet = socket.AF_INET6 if code == V6 else socket.AF_INET
    try:
        with socket.socket(inet, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect((_ROUTE_PROBE[code], 2408))
    except OSError as error:
        log.warning(
            "this host has no usable %s route (%s). %s endpoints cannot be scanned "
            "until it does - on Docker that usually means the container is on the "
            "default bridge; use network_mode: host or enable IPv6 on the network.",
            code.upper(),
            error,
            code.upper(),
        )
        return False
    return True


def reachable(family: str, refresh: bool = False) -> bool:
    """True when this host has a usable route for that address family."""
    code = normalise_family(family)
    if refresh or _routes.get(code) is None:
        _routes[code] = _probe_route(code)
    return bool(_routes[code])


def routes(refresh: bool = False) -> dict[str, bool]:
    return {family: reachable(family, refresh) for family in FAMILIES}


def available_families(refresh: bool = False) -> tuple[str, ...]:
    return tuple(family for family in FAMILIES if reachable(family, refresh))


# --------------------------------------------------------------------- #
# the probing identity
# --------------------------------------------------------------------- #


def fallback_identity() -> dict:
    """An enrolled probing identity that needs no network call at all.

    Registering a device against ``api.cloudflareclient.com`` is the nice path,
    but that host is blocked from a great many Iranian servers and Cloudflare
    rate-limits datacentre ranges hard. Without this function a failed
    registration meant no scan at all, and a *revoked* cached registration was
    worse: it scanned happily and reported every endpoint as dead forever.

    Prefers, in order: WarpEP's own cached ``warpep register`` account, WarpEP's
    bundled enrolled key, then the copy vendored above.
    """
    identity = {
        "private_key": FALLBACK_PRIVATE_KEY,
        "peer_public_key": RESPONDER_PUBLIC_KEY,
        # Zero reserved bytes on purpose: a shared probing key routes to no
        # account, and WarpEP's own scanner handshakes with them at zero too.
        "reserved": [0, 0, 0],
        "client_id": "",
        "v4": "172.16.0.2",
        "v6": "",
        "account_type": "probe",
        # Marks a key that is not ours: the deep tunnel check must never draw a
        # conclusion from it. See ``deep_verify``.
        "shared": True,
        "source": "warpep bundled (vendored)",
    }
    if _upstream is None:
        return identity
    try:
        from warpep import resolve_identity  # type: ignore

        resolved = resolve_identity()
        if not resolved.registered:
            return identity
        identity["private_key"] = resolved.keypair.private_b64
        identity["peer_public_key"] = base64.b64encode(resolved.responder_public).decode("ascii")
        identity["v4"] = getattr(resolved, "client_ip", "") or "172.16.0.2"
        identity["v6"] = getattr(resolved, "client_ip_v6", "") or ""
        identity["source"] = f"warpep {resolved.source}"
        # WarpEP's own registration *is* a real device, so its tunnel is routable
        # and the deep check can be trusted again.
        identity["shared"] = resolved.source != "account"
    except Exception as error:  # noqa: BLE001
        log.info("warpep could not hand over an identity: %s", error)
    return identity


# --------------------------------------------------------------------- #
# candidate generation
# --------------------------------------------------------------------- #


def _v6_offsets() -> tuple[int, ...]:
    """Interface ids worth trying inside a WARP /64."""
    offsets: list[int] = []
    for base in _V6_BASES:
        offsets.extend((base << 16) + host for host in range(1, 256))
        # The c0xx block is where the published control endpoints live.
        offsets.extend((base << 16) + host for host in range(0xC001, 0xC021))
    return tuple(offsets)


_V6_OFFSETS = _v6_offsets()


def _addresses_in(prefix: str) -> list[str]:
    network = ipaddress.ip_network(prefix, strict=False)
    if network.version == 6:
        base = int(network.network_address)
        return [str(ipaddress.IPv6Address(base + offset)) for offset in _V6_OFFSETS]
    if network.num_addresses <= 2:
        return [str(network.network_address)]
    return [str(host) for host in network.hosts()]


def candidates(
    family: str,
    per_prefix: int,
    rng: Optional[random.Random] = None,
) -> list[str]:
    """``per_prefix`` random addresses from every prefix of that family.

    Sampling per prefix rather than across the whole space is deliberate, and it
    is the same choice WarpEP's ``spread()`` makes: a flat random draw over a
    /24-heavy space clusters, and a scan that happens to take twenty addresses
    out of the one block being blackholed reports that nothing works at all.

    Note that IPv6 has two prefixes against IPv4's seven, so the same
    ``per_prefix`` yields far fewer IPv6 candidates. The IPv6 draw is topped up
    so both pools get a comparable number of chances rather than IPv6 scanning a
    quarter as many addresses and then being written off as filtered.
    """
    picker = rng or random
    wanted = max(1, int(per_prefix))
    code = normalise_family(family)
    if code == V6:
        wanted = max(wanted, (wanted * len(IPV4_PREFIXES)) // max(1, len(IPV6_PREFIXES)))
    out: list[str] = []
    for prefix in prefixes(code):
        pool = _addresses_in(prefix)
        if not pool:
            continue
        out.extend(pool if wanted >= len(pool) else picker.sample(pool, wanted))
    picker.shuffle(out)
    return out


def spread(rows: Sequence[dict], count: int) -> list[dict]:
    """Take one row from each distinct block first, then top up in order."""
    chosen: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        key = block_of(row["ip"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(row)
        if len(chosen) >= count:
            return chosen
    for row in rows:
        if len(chosen) >= count:
            break
        if row not in chosen:
            chosen.append(row)
    return chosen[:count]


# --------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------- #


def health(
    latency: float,
    jitter: float = 0.0,
    loss: float = 0.0,
    verified: Optional[bool] = None,
) -> int:
    """WarpEP's 0-100 health score. ``loss`` is a ratio, not a percentage.

    Loss dominates, then latency, then jitter. A proven tunnel adds a small
    bonus; a *failed* tunnel check halves the score, because an endpoint that
    completes handshakes and then swallows traffic is worse than useless.
    """
    latency = float(latency or 0.0)
    if latency <= 0:
        return 0
    score = 100.0
    score -= min(45.0, float(loss or 0.0) * 100.0 * 0.45)
    score -= min(30.0, max(0.0, latency - 40.0) / 6.0)
    score -= min(15.0, float(jitter or 0.0) / 3.0)
    if verified is True:
        score = min(100.0, score + 6.0)
    elif verified is False:
        score *= 0.5
    return max(1, min(100, int(round(score))))


def grade(score: int) -> str:
    if score <= 0:
        return "dead"
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


def badge(score: int, verified: Optional[bool] = None) -> str:
    """The mark shown next to an endpoint. Honest about what was actually proven."""
    if score <= 0:
        return "\U0001f480"
    if verified is True:
        return "\U0001f7e2"
    if verified is False:
        return "\u26a0\ufe0f"
    if score >= 85:
        return "\u2705"
    if score >= 70:
        return "\U0001f7e1"
    return "\U0001f7e0"


# --------------------------------------------------------------------- #
# the deep check
# --------------------------------------------------------------------- #


def deep_possible(identity: Optional[dict] = None) -> bool:
    """Can the tunnel check produce a meaningful verdict for this identity?"""
    if _upstream is None:
        return False
    if identity is None:
        return True
    return not bool(identity.get("shared"))


def _deep_sync(
    private_key: str,
    peer_public: str,
    client_ip: str,
    ip: str,
    port: int,
    echoes: int,
    timeout: float,
) -> tuple[bool, str, Optional[float]]:
    """Runs in a worker thread: WarpEP's own end-to-end tunnel verification."""
    from warpep import Endpoint, resolve_identity, verify_endpoint  # type: ignore

    # ``private_key`` is supplied, so this never touches the network or the
    # on-disk WarpEP account cache.
    identity = resolve_identity(private_key=private_key, peer_key=peer_public or None)
    check = verify_endpoint(
        identity.keypair,
        Endpoint(str(ip), int(port)),
        responder_public=identity.responder_public,
        client_ip=client_ip or "172.16.0.2",
        echoes=max(1, int(echoes)),
        timeout=max(1.5, float(timeout)),
    )
    return bool(check.ok), str(check.error or ""), check.avg_tunnel_ms


async def deep_verify(
    identity: dict,
    ip: str,
    port: int,
    echoes: int = 2,
    timeout: float = 3.0,
) -> Optional[bool]:
    """Does this endpoint actually carry traffic? ``None`` means "not checked".

    Never raises, and never returns ``False`` because of a local problem: a
    missing package, a thread that blew up or a probing key with no tunnel
    address of its own is not evidence against an endpoint, and treating it as
    such would empty a perfectly good pool.
    """
    if _upstream is None:
        return None
    private_key = (identity or {}).get("private_key") or ""
    if not private_key:
        return None
    if (identity or {}).get("shared"):
        # A shared probing key is enrolled enough to get handshake answers but it
        # has no routable tunnel address, so ICMP that never comes back says
        # nothing about the endpoint. Report "not checked" and move on.
        return None
    try:
        ok, reason, tunnel_ms = await asyncio.to_thread(
            _deep_sync,
            private_key,
            (identity or {}).get("peer_public_key") or "",
            (identity or {}).get("v4") or "",
            str(ip),
            int(port),
            echoes,
            timeout,
        )
    except Exception as error:  # noqa: BLE001
        log.info("deep check on %s could not run: %s", host_port(ip, port), error)
        return None
    if ok:
        log.debug("deep check passed for %s (%s ms in tunnel)", host_port(ip, port), tunnel_ms)
        return True
    log.info("deep check failed for %s: %s", host_port(ip, port), reason or "no traffic returned")
    return False


def describe() -> str:
    """One line for the admin screen: where the search space came from."""
    return f"{SOURCE}{' + deep tunnel check' if installed() else ''}"
