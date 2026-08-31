"""The WARP endpoint pools and their health model.

Kept apart from ``db`` because a WARP endpoint is not a row you write once. Each
one carries latency, jitter, a loss ratio, a smoothed score and WarpEP's 0-100
health verdict, plus the counters that let a filtered address be retired instead
of handed to the next user who presses build.

Two pools, not one
------------------
Every row knows its address ``family`` (``v4`` or ``v6``), and every read can be
scoped to one. That is what makes "an IPv4 pool and an IPv6 pool" a real thing
here rather than a filter someone remembers to apply: an Irancell user gets an
IPv6 endpoint because ``pool("v6")`` cannot return anything else.

Only healthy rows are stored
----------------------------
``upsert`` refuses anything below ``TUNE.health_floor``, so the guarantee lives
in the storage layer instead of being a promise made by whichever caller happens
to be writing. If a row is in a pool, it answered a real WireGuard handshake and
scored well enough to be worth handing to a user.

The table itself is the one ``db`` already creates on boot; the extra columns are
added here, in place, the first time the engine runs. Existing databases keep
working and nothing has to be dropped or migrated by hand.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import db, warpep
from .warptune import TUNE

log = logging.getLogger("autovless.warpstore")

TABLE = "warp_endpoints"

# Columns this module owns. ``fails`` is listed too because an old database may
# predate it and the ALTER below is cheaper than caring which release wrote it.
COLUMNS: dict[str, str] = {
    "fails": "INTEGER NOT NULL DEFAULT 0",
    "jitter": "REAL NOT NULL DEFAULT 0",
    "loss": "REAL NOT NULL DEFAULT 0",
    "score": "REAL NOT NULL DEFAULT 0",
    "ok": "INTEGER NOT NULL DEFAULT 0",
    "last_ok": "INTEGER NOT NULL DEFAULT 0",
    # Added for the two family pools.
    "family": "TEXT NOT NULL DEFAULT ''",
    "health": "INTEGER NOT NULL DEFAULT 0",
    # -1 not checked, 0 answers but carries nothing, 1 proven end to end.
    "verified": "INTEGER NOT NULL DEFAULT -1",
}

INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_warp_score ON {TABLE} (stable, fails, score)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_checked ON {TABLE} (checked_at DESC)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_family ON {TABLE} (family, stable, fails, latency)",
)

FIELDS = (
    "ip, port, family, latency, jitter, loss, score, health, verified, "
    "stable, ok, fails, last_ok, checked_at"
)

_ready = False


def score_of(latency: float, jitter: float, loss: float) -> float:
    """One number to rank endpoints by.

    Latency alone picks pretty addresses that stutter. Jitter is what a user
    actually feels on a call, and loss is what a DPI box starts doing to a tunnel
    it has decided it dislikes, so both are priced in milliseconds.
    """
    return round(
        float(latency) + float(jitter) * TUNE.jitter_weight + float(loss) * TUNE.loss_penalty,
        1,
    )


def _verified_flag(value: object) -> int:
    if value is True:
        return 1
    if value is False:
        return 0
    return -1


async def ensure_schema() -> None:
    """Add the health columns if they are missing. Safe to call on every path."""
    global _ready
    if _ready:
        return
    async with db.conn().execute(f"PRAGMA table_info({TABLE})") as cur:
        present = {row[1] for row in await cur.fetchall()}
    for name, ddl in COLUMNS.items():
        if name in present:
            continue
        await db.conn().execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}")
        log.info("warp pool: column %s added", name)
    for statement in INDEXES:
        await db.conn().execute(statement)
    # Rows written before the split carry no family. Derive it from the address
    # rather than throwing away a pool that is already warm.
    await db.conn().execute(
        f"UPDATE {TABLE} SET family = CASE WHEN instr(ip, ':') > 0 THEN 'v6' ELSE 'v4' END "
        "WHERE family IS NULL OR family = ''"
    )
    await db.conn().commit()
    _ready = True


# --------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------- #


async def upsert(rows: list[dict], floor: Optional[int] = None) -> int:
    """Write measurements back, smoothing the score instead of replacing it.

    A single lucky handshake should not promote a flaky address to the top of a
    pool and a single unlucky one should not demote a good one, so the stored
    score is an exponential average of what we have seen.

    Rows below the health floor are dropped on the way in. This is the only door
    into a pool, so that check is the whole "healthy endpoints only" guarantee.
    """
    if not rows:
        return 0
    await ensure_schema()
    ceiling = TUNE.health_floor if floor is None else int(floor)
    ts = db.now()
    weight = float(TUNE.smoothing)
    payload = []
    rejected = 0
    for row in rows:
        latency = float(row.get("latency") or 0.0)
        jitter = float(row.get("jitter") or 0.0)
        loss = float(row.get("loss") or 0.0)
        verified = row.get("verified")
        points = int(
            row.get("health") or warpep.health(latency, jitter, loss, verified=verified)
        )
        if latency <= 0 or points < ceiling:
            rejected += 1
            continue
        score = float(row.get("score") or score_of(latency, jitter, loss))
        payload.append(
            (
                str(row["ip"]),
                int(row["port"]),
                warpep.family_of(row["ip"]),
                latency,
                jitter,
                loss,
                score,
                points,
                _verified_flag(verified),
                1 if row.get("stable") else 0,
                ts,
                ts,
                weight,
                weight,
            )
        )
    if rejected:
        log.info("warp pool: %s measurement(s) rejected below health %s", rejected, ceiling)
    if not payload:
        return 0
    await db.conn().executemany(
        f"INSERT INTO {TABLE} "
        "  (ip, port, family, latency, jitter, loss, score, health, verified, "
        "   stable, ok, fails, last_ok, checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?) "
        "ON CONFLICT(ip, port) DO UPDATE SET "
        "  family  = excluded.family, "
        "  latency = excluded.latency, "
        "  jitter  = excluded.jitter, "
        "  loss    = excluded.loss, "
        f"  score   = CASE WHEN {TABLE}.score > 0 "
        f"                 THEN {TABLE}.score * (1 - ?) + excluded.score * ? "
        "                 ELSE excluded.score END, "
        "  health  = excluded.health, "
        f"  verified = CASE WHEN excluded.verified = -1 THEN {TABLE}.verified "
        "                  ELSE excluded.verified END, "
        "  stable  = excluded.stable, "
        f"  ok      = {TABLE}.ok + 1, "
        "  fails   = 0, "
        "  last_ok = excluded.last_ok, "
        "  checked_at = excluded.checked_at",
        payload,
    )
    await db.conn().commit()
    return len(payload)


async def mark_ok(
    ip: str,
    port: int,
    latency: float,
    jitter: float = 0.0,
    loss: float = 0.0,
    verified: object = None,
) -> None:
    """An endpoint answered on demand: clear its failures and refresh its numbers."""
    await ensure_schema()
    ts = db.now()
    flag = _verified_flag(verified)
    await db.execute(
        f"UPDATE {TABLE} SET latency = ?, jitter = ?, loss = ?, score = ?, health = ?, "
        "family = ?, stable = 1, verified = CASE WHEN ? = -1 THEN verified ELSE ? END, "
        "ok = ok + 1, fails = 0, last_ok = ?, checked_at = ? WHERE ip = ? AND port = ?",
        (
            float(latency),
            float(jitter),
            float(loss),
            score_of(latency, jitter, loss),
            warpep.health(latency, jitter, loss, verified=verified),
            warpep.family_of(ip),
            flag,
            flag,
            ts,
            ts,
            str(ip),
            int(port),
        ),
    )


async def mark_fail(ip: str, port: int) -> int:
    """Count a failure and stop advertising the endpoint once it hits the limit."""
    await ensure_schema()
    await db.execute(
        f"UPDATE {TABLE} SET fails = fails + 1, checked_at = ?, "
        "stable = CASE WHEN fails + 1 >= ? THEN 0 ELSE stable END, "
        "health = CASE WHEN fails + 1 >= ? THEN 0 ELSE health END "
        "WHERE ip = ? AND port = ?",
        (db.now(), int(TUNE.fail_limit), int(TUNE.fail_limit), str(ip), int(port)),
    )
    return int(
        await db.scalar(
            f"SELECT fails FROM {TABLE} WHERE ip = ? AND port = ?", (str(ip), int(port))
        )
        or 0
    )


async def drop(ip: str, port: int) -> None:
    """Delete one endpoint outright. What the agent does to a corpse."""
    await ensure_schema()
    await db.execute(f"DELETE FROM {TABLE} WHERE ip = ? AND port = ?", (str(ip), int(port)))


async def retire(fail_limit: Optional[int] = None, stale_after: Optional[int] = None) -> int:
    """Delete what is dead, and what nobody has ever managed to confirm."""
    await ensure_schema()
    ceiling = int(fail_limit or TUNE.fail_limit)
    cutoff = db.now() - int(stale_after or TUNE.stale_after)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE fails >= ? OR (checked_at < ? AND ok = 0)",
        (ceiling, cutoff),
    )
    removed = int(cursor.rowcount or 0)
    await cursor.close()
    await db.conn().commit()
    return max(0, removed)


async def purge_unhealthy(floor: Optional[int] = None) -> int:
    """Delete everything a pool is not allowed to contain.

    Belt and braces next to the check in ``upsert``: a row can rot in place after
    it was written, and a pool that quietly keeps a 0-health address is exactly
    the failure this whole feature exists to prevent.
    """
    await ensure_schema()
    ceiling = TUNE.health_floor if floor is None else int(floor)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE health < ? OR latency <= 0 OR verified = 0",
        (ceiling,),
    )
    removed = int(cursor.rowcount or 0)
    await cursor.close()
    await db.conn().commit()
    return max(0, removed)


async def trim(keep: int, family: Optional[str] = None) -> int:
    """Cap a pool. Proven rows win, then healthier ones, then the faster ones."""
    await ensure_schema()
    limit = max(2, int(keep))
    if family is None:
        await db.execute(
            f"DELETE FROM {TABLE} WHERE rowid NOT IN ("
            f"  SELECT rowid FROM {TABLE} "
            "   ORDER BY stable DESC, fails ASC, score ASC LIMIT ?)",
            (limit,),
        )
        return 0
    code = warpep.normalise_family(family)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE family = ? AND rowid NOT IN ("
        f"  SELECT rowid FROM {TABLE} WHERE family = ? "
        "   ORDER BY verified DESC, health DESC, latency ASC LIMIT ?)",
        (code, code, limit),
    )
    removed = int(cursor.rowcount or 0)
    await cursor.close()
    await db.conn().commit()
    return max(0, removed)


# --------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------- #


async def best(
    limit: int,
    stable_only: bool = True,
    max_loss: Optional[float] = None,
    max_age: Optional[int] = None,
    fail_limit: Optional[int] = None,
    family: Optional[str] = None,
) -> list[dict]:
    """Healthiest endpoints first. Cheap enough to call on every config build."""
    await ensure_schema()
    params: list = [int(fail_limit or TUNE.fail_limit)]
    sql = f"SELECT {FIELDS} FROM {TABLE} WHERE fails < ? "
    if family is not None:
        sql += "AND family = ? "
        params.append(warpep.normalise_family(family))
    if stable_only:
        sql += "AND stable = 1 "
    if max_loss is not None:
        sql += "AND loss <= ? "
        params.append(float(max_loss))
    if max_age:
        sql += "AND checked_at >= ? "
        params.append(db.now() - int(max_age))
    sql += "ORDER BY score ASC, latency ASC LIMIT ?"
    params.append(max(1, int(limit)))
    return [dict(row) for row in await db.fetch_all(sql, params)]


async def pool(family: str, limit: Optional[int] = None) -> list[dict]:
    """One family's pool, healthy rows only, ordered by ping.

    Ping order rather than score order is a deliberate difference from ``best``:
    this is what a user is handed and what the pool screen prints, and "sorted by
    ping" is the thing they asked for and can verify with their own eyes.
    """
    await ensure_schema()
    code = warpep.normalise_family(family)
    return [
        dict(row)
        for row in await db.fetch_all(
            f"SELECT {FIELDS} FROM {TABLE} "
            "WHERE family = ? AND stable = 1 AND fails = 0 AND health >= ? AND verified <> 0 "
            "ORDER BY latency ASC, health DESC LIMIT ?",
            (code, int(TUNE.health_floor), max(1, int(limit or TUNE.pool_target))),
        )
    ]


async def rows_of(family: Optional[str] = None, limit: int = 500) -> list[dict]:
    """Everything stored, healthy or not. What the full audit walks."""
    await ensure_schema()
    if family is None:
        return [
            dict(row)
            for row in await db.fetch_all(
                f"SELECT {FIELDS} FROM {TABLE} ORDER BY family ASC, latency ASC LIMIT ?",
                (max(1, int(limit)),),
            )
        ]
    return [
        dict(row)
        for row in await db.fetch_all(
            f"SELECT {FIELDS} FROM {TABLE} WHERE family = ? ORDER BY latency ASC LIMIT ?",
            (warpep.normalise_family(family), max(1, int(limit))),
        )
    ]


async def counts(family: str) -> dict:
    """How full one pool is, and how good the top of it is."""
    await ensure_schema()
    code = warpep.normalise_family(family)
    top = await db.fetch_one(
        f"SELECT ip, port, latency, health, verified FROM {TABLE} "
        "WHERE family = ? AND stable = 1 AND fails = 0 ORDER BY latency ASC LIMIT 1",
        (code,),
    )
    healthy = int(
        await db.scalar(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE family = ? AND stable = 1 AND fails = 0 AND health >= ? AND verified <> 0",
            (code, int(TUNE.health_floor)),
            default=0,
        )
        or 0
    )
    return {
        "family": code,
        "total": int(
            await db.scalar(
                f"SELECT COUNT(*) FROM {TABLE} WHERE family = ?", (code,), default=0
            )
            or 0
        ),
        "healthy": healthy,
        "proven": int(
            await db.scalar(
                f"SELECT COUNT(*) FROM {TABLE} WHERE family = ? AND verified = 1",
                (code,),
                default=0,
            )
            or 0
        ),
        "shaky": int(
            await db.scalar(
                f"SELECT COUNT(*) FROM {TABLE} WHERE family = ? AND fails > 0",
                (code,),
                default=0,
            )
            or 0
        ),
        "target": int(TUNE.pool_target),
        "full": healthy >= int(TUNE.pool_target),
        "best": round(float(top["latency"]), 1) if top is not None else None,
        "best_health": int(top["health"]) if top is not None else 0,
        "best_endpoint": warpep.host_port(top["ip"], top["port"]) if top is not None else "",
        "avg": round(
            float(
                await db.scalar(
                    f"SELECT AVG(latency) FROM {TABLE} "
                    "WHERE family = ? AND stable = 1 AND fails = 0",
                    (code,),
                    default=0.0,
                )
                or 0.0
            ),
            1,
        ),
        "updated_at": int(
            await db.scalar(
                f"SELECT MAX(checked_at) FROM {TABLE} WHERE family = ?", (code,), default=0
            )
            or 0
        ),
    }


async def stats() -> dict:
    await ensure_schema()
    top = await db.fetch_one(
        f"SELECT ip, port, latency, score FROM {TABLE} "
        "WHERE stable = 1 AND fails = 0 ORDER BY score ASC LIMIT 1"
    )
    return {
        "total": int(await db.scalar(f"SELECT COUNT(*) FROM {TABLE}")),
        "stable": int(
            await db.scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE stable = 1 AND fails = 0")
        ),
        "fast": int(
            await db.scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE stable = 1 AND score < 300")
        ),
        "shaky": int(await db.scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE fails > 0")),
        "best": round(float(top["latency"]), 1) if top is not None else None,
        "best_score": round(float(top["score"]), 1) if top is not None else None,
        "best_endpoint": warpep.host_port(top["ip"], top["port"]) if top is not None else "",
        "loss": round(
            float(await db.scalar(f"SELECT AVG(loss) FROM {TABLE} WHERE stable = 1", default=0.0) or 0.0),
            3,
        ),
        "v4": int(
            await db.scalar(
                f"SELECT COUNT(*) FROM {TABLE} WHERE family = 'v4' AND stable = 1 AND fails = 0",
                default=0,
            )
            or 0
        ),
        "v6": int(
            await db.scalar(
                f"SELECT COUNT(*) FROM {TABLE} WHERE family = 'v6' AND stable = 1 AND fails = 0",
                default=0,
            )
            or 0
        ),
        "updated_at": int(await db.scalar(f"SELECT MAX(checked_at) FROM {TABLE}", default=0) or 0),
        "users": int(await db.scalar("SELECT COUNT(*) FROM warp_users")),
    }


async def snapshot(limit: Optional[int] = None) -> list[dict]:
    """The rows worth publishing outside the bot."""
    size = int(limit or TUNE.export_limit)
    rows = await best(size, stable_only=True)
    return rows or await best(size, stable_only=False)
