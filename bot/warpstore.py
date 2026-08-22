"""The WARP endpoint pool and its health model.

Kept apart from ``db`` because a WARP endpoint is not a row you write once. Each
one carries latency, jitter, a loss ratio and a smoothed score, plus the
counters that let a filtered address be retired instead of handed to the next
user who presses build.

The table itself is the one ``db`` already creates on boot; the extra columns are
added here, in place, the first time the engine runs. Existing databases keep
working and nothing has to be dropped or migrated by hand.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import db
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
}

INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_warp_score ON {TABLE} (stable, fails, score)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_checked ON {TABLE} (checked_at DESC)",
)

FIELDS = "ip, port, latency, jitter, loss, score, stable, ok, fails, last_ok, checked_at"

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
    await db.conn().commit()
    _ready = True


async def upsert(rows: list[dict]) -> int:
    """Write measurements back, smoothing the score instead of replacing it.

    A single lucky handshake should not promote a flaky address to the top of the
    pool, and a single unlucky one should not demote a good one, so the stored
    score is an exponential average of what we have seen.
    """
    if not rows:
        return 0
    await ensure_schema()
    ts = db.now()
    weight = float(TUNE.smoothing)
    payload = []
    for row in rows:
        latency = float(row.get("latency") or 0.0)
        jitter = float(row.get("jitter") or 0.0)
        loss = float(row.get("loss") or 0.0)
        score = float(row.get("score") or score_of(latency, jitter, loss))
        payload.append(
            (
                str(row["ip"]),
                int(row["port"]),
                latency,
                jitter,
                loss,
                score,
                1 if row.get("stable") else 0,
                ts,
                ts,
                weight,
                weight,
            )
        )
    await db.conn().executemany(
        f"INSERT INTO {TABLE} "
        "  (ip, port, latency, jitter, loss, score, stable, ok, fails, last_ok, checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?) "
        "ON CONFLICT(ip, port) DO UPDATE SET "
        "  latency = excluded.latency, "
        "  jitter  = excluded.jitter, "
        "  loss    = excluded.loss, "
        f"  score   = CASE WHEN {TABLE}.score > 0 "
        f"                 THEN {TABLE}.score * (1 - ?) + excluded.score * ? "
        "                 ELSE excluded.score END, "
        "  stable  = excluded.stable, "
        f"  ok      = {TABLE}.ok + 1, "
        "  fails   = 0, "
        "  last_ok = excluded.last_ok, "
        "  checked_at = excluded.checked_at",
        payload,
    )
    await db.conn().commit()
    return len(payload)


async def best(
    limit: int,
    stable_only: bool = True,
    max_loss: Optional[float] = None,
    max_age: Optional[int] = None,
    fail_limit: Optional[int] = None,
) -> list[dict]:
    """Healthiest endpoints first. Cheap enough to call on every config build."""
    await ensure_schema()
    params: list = [int(fail_limit or TUNE.fail_limit)]
    sql = f"SELECT {FIELDS} FROM {TABLE} WHERE fails < ? "
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


async def mark_ok(ip: str, port: int, latency: float, jitter: float = 0.0, loss: float = 0.0) -> None:
    """An endpoint answered on demand: clear its failures and refresh its numbers."""
    await ensure_schema()
    ts = db.now()
    await db.execute(
        f"UPDATE {TABLE} SET latency = ?, jitter = ?, loss = ?, score = ?, stable = 1, "
        "ok = ok + 1, fails = 0, last_ok = ?, checked_at = ? WHERE ip = ? AND port = ?",
        (
            float(latency),
            float(jitter),
            float(loss),
            score_of(latency, jitter, loss),
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
        "stable = CASE WHEN fails + 1 >= ? THEN 0 ELSE stable END "
        "WHERE ip = ? AND port = ?",
        (db.now(), int(TUNE.fail_limit), str(ip), int(port)),
    )
    return int(
        await db.scalar(
            f"SELECT fails FROM {TABLE} WHERE ip = ? AND port = ?", (str(ip), int(port))
        )
        or 0
    )


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


async def trim(keep: int) -> None:
    """Cap the pool. Stable rows win, then the ones with a cheaper score."""
    await ensure_schema()
    await db.execute(
        f"DELETE FROM {TABLE} WHERE rowid NOT IN ("
        f"  SELECT rowid FROM {TABLE} ORDER BY stable DESC, fails ASC, score ASC LIMIT ?)",
        (max(4, int(keep)),),
    )


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
        "best_endpoint": f"{top['ip']}:{top['port']}" if top is not None else "",
        "loss": round(
            float(await db.scalar(f"SELECT AVG(loss) FROM {TABLE} WHERE stable = 1", default=0.0) or 0.0),
            3,
        ),
        "updated_at": int(await db.scalar(f"SELECT MAX(checked_at) FROM {TABLE}", default=0) or 0),
        "users": int(await db.scalar("SELECT COUNT(*) FROM warp_users")),
    }


async def snapshot(limit: Optional[int] = None) -> list[dict]:
    """The rows worth publishing outside the bot."""
    size = int(limit or TUNE.export_limit)
    rows = await best(size, stable_only=True)
    return rows or await best(size, stable_only=False)
