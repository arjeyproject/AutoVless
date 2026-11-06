"""Operator-aware endpoint selection for WireGuard / WARP.

The scanner measures every endpoint from the bot's own network, which says
nothing about how a given Iranian carrier reaches that address. This layer
closes that gap with two sources of truth:

1. **Profile priors.** Every operator carries a known port affinity and an MTU
   that works behind its CGNAT (``operators.wg_profile``). A pool row on an
   operator's preferred ports is worth more to that operator's users than a
   raw millisecond saved somewhere else.

2. **Learned wins.** Every real handshake benchmark a user runs (``wg:bench``)
   reports measured latencies tagged with that user's operator. Wins accumulate
   per (ip, port, operator), so over a few days the pool knows which endpoints
   actually answer on MCI, on Irancell, on Rightel - instead of guessing.

``pick`` blends both: candidates still come from the healthy family pool (an
endpoint that failed the real handshake never ships, whatever its history),
then are re-ranked for the requesting operator. The leaderboard and counts
feed the admin screen and the user's operator picker, so both can show *why*
an operator is or is not served well right now.
"""

from __future__ import annotations

import logging

from . import db, operators
from .config import settings

log = logging.getLogger("autovless.warpops")

TABLE = "warp_ops"

SCHEMA = """
CREATE TABLE IF NOT EXISTS warp_ops (
    ip         TEXT    NOT NULL,
    port       INTEGER NOT NULL,
    operator   TEXT    NOT NULL,
    latency    REAL    NOT NULL DEFAULT 0,
    wins       INTEGER NOT NULL DEFAULT 0,
    tests      INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ip, port, operator)
);
CREATE INDEX IF NOT EXISTS idx_warp_ops_rank ON warp_ops (operator, wins DESC, latency ASC);
"""

_schema_done = False


async def ensure_schema() -> None:
    global _schema_done
    if _schema_done:
        return
    connection = db.conn()
    await connection.executescript(SCHEMA)
    await connection.commit()
    _schema_done = True


# --------------------------------------------------------------------- reads


async def scores_for(operator: str, limit: int = 1000) -> dict[tuple[str, int], dict]:
    """Learned rows for one operator, keyed by (ip, port)."""
    await ensure_schema()
    rows = await db.fetch_all(
        f"SELECT ip, port, latency, wins, tests FROM {TABLE} "
        "WHERE operator = ? AND tests > 0 "
        "ORDER BY wins DESC, latency ASC LIMIT ?",
        (str(operator or ""), max(1, int(limit))),
    )
    return {(str(r["ip"]), int(r["port"])): dict(r) for r in rows}


async def leaderboard(operator: str, limit: int = 10) -> list[dict]:
    """Endpoints that actually answered for this operator, best first."""
    await ensure_schema()
    rows = await db.fetch_all(
        f"SELECT ip, port, latency, wins, tests, updated_at FROM {TABLE} "
        "WHERE operator = ? AND tests > 0 "
        "ORDER BY (wins * 1.0 / tests) DESC, latency ASC LIMIT ?",
        (str(operator or ""), max(1, int(limit))),
    )
    return [dict(r) for r in rows]


async def counts() -> dict[str, dict]:
    """Per operator: how many endpoints have evidence, and how many are winning."""
    await ensure_schema()
    rows = await db.fetch_all(
        f"SELECT operator, COUNT(*) AS known, "
        f"SUM(CASE WHEN wins > 0 THEN 1 ELSE 0 END) AS proven "
        f"FROM {TABLE} WHERE tests > 0 GROUP BY operator"
    )
    out = {code: {"known": 0, "proven": 0} for code in operators.OPERATORS}
    for row in rows:
        out[str(row["operator"])] = {
            "known": int(row["known"] or 0),
            "proven": int(row["proven"] or 0),
        }
    return out


# -------------------------------------------------------------------- writes


async def record(operator: str, measured: list[dict]) -> None:
    """Log one benchmark round for one operator.

    ``measured`` is ``[{ip, port, latency}, ...]`` best first. Every row gets a
    test; the top rows share the wins, weighted by how far ahead of the rest
    they finished - so a clear winner moves the leaderboard faster than three
    endpoints that all answered about the same.
    """
    await ensure_schema()
    code = str(operator or "").strip()
    if not code or not measured:
        return
    best = min(
        (float(row.get("latency") or 0) for row in measured if float(row.get("latency") or 0) > 0),
        default=0.0,
    )
    if best <= 0:
        return
    now = db.now()
    connection = db.conn()
    for row in measured[: settings.warp_per_config * 2]:
        latency = float(row.get("latency") or 0)
        if latency <= 0:
            continue
        # The outright winner and everything within 25% of it earns a win; the
        # rest earn only the test, so the leaderboard separates leaders from
        # the pack instead of rewarding merely having answered.
        win = 1 if latency <= max(best * 1.25, best + 30) else 0
        try:
            await connection.execute(
                f"INSERT INTO {TABLE} (ip, port, operator, latency, wins, tests, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?) "
                "ON CONFLICT (ip, port, operator) DO UPDATE SET "
                "latency = excluded.latency, "
                "wins = wins + ?, tests = tests + 1, updated_at = excluded.updated_at",
                (str(row["ip"]), int(row["port"]), code, latency, win, now, win),
            )
        except Exception:  # noqa: BLE001
            log.debug("could not record a warp_ops row", exc_info=True)
    await connection.commit()


# -------------------------------------------------------------------- picking


def _prior(operator: str, row: dict) -> float:
    """Profile prior: lower is better, in the same units as latency."""
    profile = operators.wg_profile(operator)
    penalty = 0.0
    port = int(row.get("port") or 0)
    preferred = profile["ports"]
    if preferred and port in preferred:
        penalty -= 40.0
    elif preferred:
        penalty += 25.0
    if profile.get("ipv6_ok") and str(row.get("family") or "") == "v6":
        penalty -= 20.0
    return penalty


def rank_for(candidates: list[dict], operator: str, learned: dict[tuple[str, int], dict]) -> list[dict]:
    """Re-rank family-pool candidates for one operator. Pure, no I/O."""
    def key(row: dict) -> tuple[float, float]:
        stats = learned.get((str(row.get("ip")), int(row.get("port") or 0)))
        if stats:
            tests = max(1, int(stats["tests"]))
            reliability = int(stats["wins"]) / tests
            return (0.0 - reliability, float(stats["latency"]) + _prior(operator, row))
        return (1.0, float(row.get("latency") or 9999) + _prior(operator, row))

    return sorted(candidates, key=key)


async def pick(family: str, operator: str, count: int | None = None) -> list[dict]:
    """Healthy endpoints of one family, ranked for one operator."""
    from .warppool import warp_pool

    wanted = max(1, int(count or settings.warp_per_config))
    candidates = await warp_pool.pick(family, count=max(wanted * 3, wanted))
    if not candidates:
        return []
    learned = await scores_for(operator)
    ranked = rank_for(candidates, operator, learned)
    return ranked[:wanted]
