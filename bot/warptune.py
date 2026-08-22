"""Field knobs for the WARP endpoint engine.

These sit apart from ``config.Settings`` on purpose. The endpoint engine is the
one part of this bot that gets re-tuned in the field, usually over SSH while a
fresh filtering rule is rolling out, and none of it should mean touching the
frozen settings object every other module depends on.

Read once from the environment. The defaults suit a single small VPS serving a
few hundred users.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _raw(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = _raw(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(low, min(high, value))


def _float(name: str, default: float, low: float, high: float) -> float:
    raw = _raw(name)
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(low, min(high, value))


def _flag(name: str, default: bool) -> bool:
    raw = _raw(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Tune:
    """Everything the endpoint engine reads at runtime."""

    # ------------------------------------------------------------- sweeps
    quick_sample: int      # addresses per prefix for a user triggered sweep
    full_gap: int          # seconds between two full sweeps
    quick_gap: int         # seconds between two quick sweeps
    user_cooldown: int     # seconds between two presses of the rescan button

    # ------------------------------------------------------------ probing
    probes: int            # handshakes per candidate in the verify pass
    probe_gap: float       # spacing between those handshakes
    probe_retries: int     # second chances per handshake, UDP being UDP
    loss_max: float        # above this loss ratio an endpoint is not stable

    # ------------------------------------------------------------ scoring
    jitter_weight: float   # how much jitter costs, in latency milliseconds
    loss_penalty: float    # how much a full loss ratio costs, same unit
    smoothing: float       # weight of a new measurement against the old score

    # ------------------------------------------------------ pool hygiene
    fail_limit: int        # consecutive failures before an endpoint is retired
    stale_after: int       # seconds before an unconfirmed row is dropped

    # ---------------------------------------------------------- watchdog
    watch_enabled: bool
    watch_interval: int    # seconds between re-checks of the endpoints in use
    watch_size: int        # how many of the best endpoints get re-checked

    # ------------------------------------------------------------ export
    export_limit: int      # rows written by scripts/publish_warp.py


def load() -> Tune:
    return Tune(
        quick_sample=_int("WARP_QUICK_SAMPLE", 3, 1, 24),
        full_gap=_int("WARP_FULL_GAP", 240, 30, 3600),
        quick_gap=_int("WARP_QUICK_GAP", 45, 5, 900),
        user_cooldown=_int("WARP_USER_COOLDOWN", 60, 0, 900),
        probes=_int("WARP_PROBES", 3, 2, 6),
        probe_gap=_float("WARP_PROBE_GAP", 0.7, 0.1, 5.0),
        probe_retries=_int("WARP_PROBE_RETRIES", 1, 0, 3),
        loss_max=_float("WARP_LOSS_MAX", 0.34, 0.0, 0.9),
        jitter_weight=_float("WARP_JITTER_WEIGHT", 0.7, 0.0, 5.0),
        loss_penalty=_float("WARP_LOSS_PENALTY", 600.0, 0.0, 5000.0),
        smoothing=_float("WARP_SMOOTHING", 0.4, 0.05, 1.0),
        fail_limit=_int("WARP_FAIL_LIMIT", 3, 1, 10),
        stale_after=_int("WARP_STALE_AFTER", 21_600, 600, 604_800),
        watch_enabled=_flag("WARP_WATCH", True),
        watch_interval=_int("WARP_WATCH_INTERVAL", 150, 30, 3600),
        watch_size=_int("WARP_WATCH_SIZE", 8, 2, 40),
        export_limit=_int("WARP_EXPORT_LIMIT", 40, 1, 500),
    )


TUNE = load()
