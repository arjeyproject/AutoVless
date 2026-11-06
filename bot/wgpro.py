"""WireGuard pro layer: per-user tuning, measured endpoint benchmarks.

Two jobs, both born from real complaints:

**Per-user tuning.** One fixed obfuscation profile and one fixed MTU cannot be
right for every carrier. MCI on an old SIM behaves nothing like Wi-Fi, and an
iPhone on Irancell needs a different file from an Android on the same network.
So the important knobs moved into a settings screen: how aggressive the junk
train is (``intensity``), how big the packets are allowed to be (``mtu``), and
which DNS servers the tunnel resolves with (``dns``). The preferences live in
the ``options`` table under one key per user, so they survive a restart and are
restored by the identity backup exactly as the user left them.

**The benchmark.** "Which endpoint is fastest *for me*" is a question the pool
cannot answer alone: its ranking comes from the bot's own network path, and the
user's path can be an entirely different country and carrier. The benchmark
fires real handshakes from the probe code in ``wireguard`` against the healthiest
stored endpoints, using the *user's own identity* - same keys, same reserved
bytes - and reorders the user's endpoint list by what actually answered.

Nothing here obfuscates blindly: S1/S2 and H1-H4 stay at their WireGuard
defaults in every grade, because the far end is Cloudflare's own peer and drops
anything it cannot parse. Only the junk train and the I1 decoy change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Optional, Sequence

from . import db, warpstore, wireguard
from .config import settings

log = logging.getLogger("autovless.wgpro")

# --------------------------------------------------------------------- #
# the knobs, in the order the settings screen shows them
# --------------------------------------------------------------------- #

INTENSITIES: tuple[str, ...] = ("normal", "strong", "ultra")
MTU_MODES: tuple[str, ...] = ("auto", "safe", "balanced", "max")
MTU_VALUES: dict[str, int] = {"safe": 1280, "balanced": 1380, "max": 1420}

# Real resolver pairs. The Iranian ones exist because the tunnel's own DNS has
# to answer *inside* the tunnel; a blocked resolver means a connected config
# that cannot load anything, which users report as "the VPN is broken".
DNS_CHOICES: tuple[tuple[str, str], ...] = (
    ("cf", "1.1.1.1, 1.0.0.1"),
    ("google", "8.8.8.8, 8.8.4.4"),
    ("shecan", "178.22.122.100, 185.51.200.2"),
    ("electro", "78.157.42.100, 78.157.42.101"),
    ("radar", "10.202.10.10, 10.202.10.11"),
)

DEFAULT_PREFS: dict[str, Any] = {"intensity": "normal", "mtu": "auto", "dns": "cf"}

_INTENSITY_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    # normal is whatever ``warp.obfuscation`` derives, kept for continuity.
    "strong": {"jc": (8, 13), "jmin": (180, 320), "jmax": (1100, 1700)},
    "ultra": {"jc": (10, 15), "jmin": (240, 400), "jmax": (1400, 2000)},
}


def _key(tg_id: int) -> str:
    return f"wgpro:{int(tg_id)}"


def _clean(prefs: dict) -> dict:
    out = dict(DEFAULT_PREFS)
    out.update({k: v for k, v in (prefs or {}).items() if k in DEFAULT_PREFS})
    if out["intensity"] not in INTENSITIES:
        out["intensity"] = "normal"
    if out["mtu"] not in MTU_MODES:
        out["mtu"] = "auto"
    if out["dns"] not in {code for code, _ in DNS_CHOICES}:
        out["dns"] = "cf"
    return out


async def prefs_of(tg_id: int) -> dict:
    """The user's saved tuning, defaults filled in."""
    try:
        raw = await db.get_option(_key(tg_id), "")
        return _clean(json.loads(raw) if raw else {})
    except (ValueError, TypeError):
        return dict(DEFAULT_PREFS)


async def save_prefs(tg_id: int, **changes: Any) -> dict:
    prefs = await prefs_of(tg_id)
    prefs.update({k: v for k, v in changes.items() if k in DEFAULT_PREFS})
    prefs = _clean(prefs)
    await db.set_option(_key(tg_id), json.dumps(prefs, separators=(",", ":")))
    await db.log_event("wgpro", tg_id, json.dumps(prefs, separators=(",", ":")))
    return prefs


# --------------------------------------------------------------------- #
# obfuscation grades
# --------------------------------------------------------------------- #


def _graded_profile(seed: str, grade: str) -> dict:
    """A denser junk train for the stronger grades, stable per seed."""
    ranges = _INTENSITY_RANGES[grade]
    rng = random.Random(f"{settings.secret_key}:{seed}:{grade}")
    return {
        "jc": rng.randint(*ranges["jc"]),
        "jmin": rng.randint(*ranges["jmin"]),
        "jmax": rng.randint(*ranges["jmax"]),
        "i1": "",
    }


def profile_for(identity: dict, prefs: dict) -> dict:
    """The obfuscation profile this user's intensity calls for.

    ``ultra`` also carries the QUIC-shaped I1 decoy from ``warp.obfuscation``;
    the export layer turns it into an AmneziaWG 1.5 signature config. ``strong``
    and ``normal`` keep I1 empty on purpose - the decoy changes what the first
    packet looks like and is the one knob that can backfire on a picky carrier.
    """
    from .warp import obfuscation  # local import: warp imports config only

    intensity = (prefs or {}).get("intensity", "normal")
    if intensity not in _INTENSITY_RANGES:
        return obfuscation(identity.get("private_key", ""))

    profile = _graded_profile(identity.get("private_key", ""), intensity)
    if intensity == "ultra":
        profile["i1"] = obfuscation(identity.get("private_key", "")).get("i1", "")
    return profile


def wants_signature(prefs: dict) -> bool:
    """Ultra means the I1 decoy is emitted, which is an awg2-style config."""
    return (prefs or {}).get("intensity") == "ultra"


def mtu_for(prefs: dict) -> Optional[int]:
    """``None`` means auto: the platform profile decides, as before."""
    mode = (prefs or {}).get("mtu", "auto")
    return MTU_VALUES.get(mode)


def dns_for(prefs: dict) -> Optional[str]:
    """``None`` means the platform default, as before."""
    code = (prefs or {}).get("dns", "cf")
    table = dict(DNS_CHOICES)
    return table.get(code)


async def export_params(tg_id: int, identity: dict) -> dict:
    """Everything a renderer needs to honour this user's tuning.

    One call per export: the graded obfuscation profile, the MTU override (or
    ``None`` to let the platform profile decide), the tunnel DNS (or ``None``
    for the platform default), and whether the identity asked for the
    AmneziaWG 1.5 signature config. Every delivery path - bot exports, the
    mini app, the download gateway - goes through this, so the settings screen
    never lies about what applies.
    """
    prefs = await prefs_of(tg_id)
    return {
        "profile": profile_for(identity, prefs),
        "mtu": mtu_for(prefs),
        "dns": dns_for(prefs),
        "signature": wants_signature(prefs),
    }


def summary(prefs: dict, lang: str) -> str:
    """One line describing the tuning, for the settings screen and backups."""
    from .i18n import t

    mtu = (prefs or {}).get("mtu", "auto")
    mtu_text = t(lang, f"pro.mtu_{mtu}")
    dns = (prefs or {}).get("dns", "cf")
    dns_text = t(lang, f"pro.dns_{dns}")
    intensity = t(lang, f"pro.intensity_{(prefs or {}).get('intensity', 'normal')}")
    return f"{intensity} · {mtu_text} · {dns_text}"


# --------------------------------------------------------------------- #
# the benchmark
# --------------------------------------------------------------------- #


async def _probe_one(
    row: dict,
    identity: dict,
    timeout: float,
) -> Optional[dict]:
    """One real handshake against one endpoint, with the user's own keys."""
    reserved = identity.get("reserved") or [0, 0, 0]
    rtt = await wireguard.stable_handshake(
        str(row["ip"]),
        int(row["port"]),
        identity["private_key"],
        identity["peer_public_key"],
        reserved=reserved,
        timeout=timeout,
    )
    if rtt is None:
        return None
    return {"ip": str(row["ip"]), "port": int(row["port"]), "latency": rtt}


async def benchmark(
    identity: dict,
    family: Optional[str] = None,
    count: int = 10,
    concurrency: int = 4,
) -> tuple[list[dict], list[dict]]:
    """Measure the healthiest stored endpoints from this host, live.

    Returns ``(measured, candidates)``: the endpoints that answered, sorted
    fastest first, and the full candidate list that was tried. An empty
    ``measured`` with a full ``candidates`` is a real diagnosis - the pool
    answered somewhere else but not from here - so the caller can say so.

    ``family`` picks one address family, or ``None`` for the best of both.
    """
    candidates = await warpstore.best(max(4, min(count, 24)), stable_only=True, family=family)
    if not candidates:
        candidates = await warpstore.best(max(4, min(count, 24)), stable_only=False)
    if not candidates:
        return [], []

    timeout = max(1.0, min(settings.warp_scan_timeout, 3.0))
    gate = asyncio.Semaphore(max(1, concurrency))

    async def guarded(row: dict) -> Optional[dict]:
        async with gate:
            try:
                return await _probe_one(row, identity, timeout)
            except (OSError, ValueError, KeyError) as error:  # noqa: BLE001
                log.info("benchmark probe failed for %s:%s: %s", row.get("ip"), row.get("port"), error)
                return None

    results = await asyncio.gather(*(guarded(row) for row in candidates))
    measured = sorted(
        (row for row in results if row is not None), key=lambda row: row["latency"]
    )
    return measured, candidates


# --------------------------------------------------------------------- #
# the identity backup
# --------------------------------------------------------------------- #

_BACKUP_IDENTITY_FIELDS: tuple[str, ...] = (
    "private_key",
    "peer_public_key",
    "client_id",
    "reserved",
    "v4",
    "v6",
    "device_id",
    "token",
    "account_type",
    "license",
    "api",
)


def backup_document(identity: dict, endpoints: Sequence[dict], prefs: dict) -> str:
    """The user's whole WARP identity as portable JSON.

    Restoring this on a new chat rebuilds the same tunnel without touching
    Cloudflare's registration API, which is itself blocked on some networks -
    that is the whole reason the backup exists.
    """
    import time as _time

    payload = {
        "format": "autovless-warp-backup",
        "version": 2,
        "brand": settings.brand,
        "created_at": int(_time.time()),
        "identity": {field: identity.get(field) for field in _BACKUP_IDENTITY_FIELDS},
        "endpoints": [
            {"ip": row.get("ip"), "port": row.get("port")} for row in (endpoints or [])[:8]
        ],
        "prefs": _clean(prefs),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def parse_backup(text: str) -> tuple[dict, list[dict], dict]:
    """Validate a pasted or uploaded backup. Raises ``ValueError`` with a reason.

    Only the two fields a config cannot live without are hard requirements;
    everything else is optional and filled in from what the file carries.
    """
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ValueError("not JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("not an object")

    fmt = str(payload.get("format") or "")
    if fmt and fmt != "autovless-warp-backup":
        raise ValueError("wrong format")

    identity = payload.get("identity") or {}
    if not isinstance(identity, dict):
        raise ValueError("identity missing")

    private = str(identity.get("private_key") or "").strip()
    public = str(identity.get("peer_public_key") or "").strip()
    if not private or not public:
        raise ValueError("keys missing")
    try:
        wireguard.decode_key(private)
        wireguard.decode_key(public)
    except Exception as error:  # noqa: BLE001
        raise ValueError("keys unreadable") from error

    clean_identity = {field: identity.get(field) for field in _BACKUP_IDENTITY_FIELDS}
    clean_identity["private_key"] = private
    clean_identity["peer_public_key"] = public
    if not clean_identity.get("reserved"):
        clean_identity["reserved"] = [0, 0, 0]
    if not clean_identity.get("account_type"):
        clean_identity["account_type"] = "free"

    endpoints: list[dict] = []
    for row in payload.get("endpoints") or []:
        if isinstance(row, dict) and row.get("ip") and row.get("port"):
            try:
                endpoints.append({"ip": str(row["ip"]), "port": int(row["port"])})
            except (TypeError, ValueError):
                continue

    return clean_identity, endpoints, _clean(payload.get("prefs") or {})
