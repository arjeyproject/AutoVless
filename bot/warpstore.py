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

Rows an admin pinned by hand
----------------------------
``manual = 1`` marks an endpoint typed into the admin panel (see
``bot.warpmanual``). It changes three things and nothing else:

  * hygiene leaves it alone. ``retire``, ``purge_unhealthy`` and ``trim`` all
    skip manual rows, because a scanner cap silently deleting the address an
    admin just entered is indistinguishable from the feature being broken;
  * ``drop`` sidelines it (``stable = 0``, ``health = 0``) instead of deleting
    it, so a manual endpoint that dies is still on the screen that owns it and
    the agent can revive it on a later pass;
  * it can be stored *untested* when this host has no route for its family, with
    ``latency = 0`` and ``verified = -1``. Those rows sort behind every measured
    endpoint, so a proven address always goes out first.

What a manual row does **not** get is a pass on health. ``pool()`` filters it by
exactly the same floor as everything else, so a dead pinned endpoint is never
handed to a user.

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

# Ranking score given to a manual row that could not be measured here. Score is
# only ever used to sort, so a deliberately terrible one keeps an untested
# address behind everything real without pretending it is slow.
MANUAL_SCORE = 9999.0

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
    # 1 when an admin entered this endpoint by hand.
    "manual": "INTEGER NOT NULL DEFAULT 0",
}

INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_warp_score ON {TABLE} (stable, fails, score)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_checked ON {TABLE} (checked_at DESC)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_family ON {TABLE} (family, stable, fails, latency)",
    f"CREATE INDEX IF NOT EXISTS idx_warp_manual ON {TABLE} (manual, family)",
)

FIELDS = (
    "ip, port, family, latency, jitter, loss, score, health, verified, "
    "stable, manual, ok, fails, last_ok, checked_at"
)

# Untested rows carry ``latency = 0``, so ordering by ping alone would put them
# first. This keeps them last without inventing a number for them.
BY_PING = "CASE WHEN latency > 0 THEN 0 ELSE 1 END, latency ASC, health DESC"

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
    into a pool for measurements, so that check is the whole "healthy endpoints
    only" guarantee. The ``manual`` flag is never written here and never cleared
    here either: a scan rediscovering a pinned address must not unpin it.
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


async def add_manual(rows: list[dict], tested: bool = True) -> int:
    """Pin endpoints an admin entered by hand into their family's pool.

    Two shapes go through here and the difference is honest in the row itself:

      * ``tested=True`` - the caller measured the endpoint for real, so the row
        carries its latency, jitter, loss and health exactly like a scanned one.
        ``bot.warpmanual`` only passes rows that already cleared the floor.
      * ``tested=False`` - this host has no route for that family, so no
        handshake was possible from here. The row is stored with ``latency = 0``,
        ``verified = -1`` and a deliberately terrible ranking score: it is
        available to users, and it is the last thing handed out.
    """
    if not rows:
        return 0
    await ensure_schema()
    ts = db.now()
    floor = int(TUNE.health_floor)
    payload = []
    for row in rows:
        ip = str(row["ip"])
        port = int(row["port"])
        if tested:
            latency = float(row.get("latency") or 0.0)
            jitter = float(row.get("jitter") or 0.0)
            loss = float(row.get("loss") or 0.0)
            verified = row.get("verified")
            points = int(
                row.get("health") or warpep.health(latency, jitter, loss, verified=verified)
            )
            score = float(row.get("score") or score_of(latency, jitter, loss))
        else:
            latency = jitter = loss = 0.0
            verified = None
            points = max(floor, int(row.get("health") or floor))
            score = MANUAL_SCORE
        payload.append(
            (
                ip,
                port,
                warpep.family_of(ip),
                latency,
                jitter,
                loss,
                score,
                points,
                _verified_flag(verified),
                ts,
                ts,
            )
        )
    await db.conn().executemany(
        f"INSERT INTO {TABLE} "
        "  (ip, port, family, latency, jitter, loss, score, health, verified, "
        "   stable, manual, ok, fails, last_ok, checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 0, ?, ?) "
        "ON CONFLICT(ip, port) DO UPDATE SET "
        "  manual  = 1, "
        "  family  = excluded.family, "
        "  latency = excluded.latency, "
        "  jitter  = excluded.jitter, "
        "  loss    = excluded.loss, "
        "  score   = excluded.score, "
        "  health  = excluded.health, "
        "  verified = excluded.verified, "
        "  stable  = 1, "
        "  fails   = 0, "
        "  last_ok = excluded.last_ok, "
        "  checked_at = excluded.checked_at",
        payload,
    )
    await db.conn().commit()
    log.info(
        "warp pool: %s manual endpoint(s) pinned (%s)",
        len(payload),
        "measured" if tested else "untested, no route here",
    )
    return len(payload)


async def mark_ok(
    ip: str,
    port: int,
    latency: float,
    jitter: float = 0.0,
    loss: float = 0.0,
    verified: object = None,
) -> None:
    """An endpoint answered on demand: clear its failures and refresh its numbers.

    This is also how a sidelined manual endpoint comes back to life: the agent
    re-probes everything stored, and a manual row that answers again is stable,
    healthy and back in the pool without anybody typing it in a second time.
    """
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


async def drop(ip: str, port: int) -> str:
    """Delete one endpoint outright. What the agent does to a corpse.

    Unless an admin typed it in. A manual endpoint is sidelined instead:
    ``stable = 0`` and ``health = 0`` keep it out of every pool read, and it
    stays on the manual screen marked dead so the person who entered it can see
    what happened. If it starts answering again the agent's next pass revives it.
    """
    await ensure_schema()
    row = await db.fetch_one(
        f"SELECT manual FROM {TABLE} WHERE ip = ? AND port = ?", (str(ip), int(port))
    )
    if row is not None and int(row["manual"] or 0):
        await db.execute(
            f"UPDATE {TABLE} SET stable = 0, health = 0, fails = fails + 1, checked_at = ? "
            "WHERE ip = ? AND port = ?",
            (db.now(), str(ip), int(port)),
        )
        log.info(
            "warp pool: manual endpoint %s sidelined, not deleted",
            warpep.host_port(ip, port),
        )
        return "sidelined"
    await db.execute(f"DELETE FROM {TABLE} WHERE ip = ? AND port = ?", (str(ip), int(port)))
    return "deleted"


async def drop_manual(ip: str, port: int) -> None:
    """Delete a pinned endpoint for real. Only the admin screen calls this."""
    await ensure_schema()
    await db.execute(
        f"DELETE FROM {TABLE} WHERE ip = ? AND port = ? AND manual = 1",
        (str(ip), int(port)),
    )


async def clear_manual(family: Optional[str] = None) -> int:
    """Forget every hand entered endpoint, of one family or of both."""
    await ensure_schema()
    if family is None:
        cursor = await db.conn().execute(f"DELETE FROM {TABLE} WHERE manual = 1")
    else:
        cursor = await db.conn().execute(
            f"DELETE FROM {TABLE} WHERE manual = 1 AND family = ?",
            (warpep.normalise_family(family),),
        )
    removed = int(cursor.rowcount or 0)
    await cursor.close()
    await db.conn().commit()
    return max(0, removed)


async def retire(fail_limit: Optional[int] = None, stale_after: Optional[int] = None) -> int:
    """Delete what is dead, and what nobody has ever managed to confirm.

    Manual rows are exempt. They are configuration, not scan output.
    """
    await ensure_schema()
    ceiling = int(fail_limit or TUNE.fail_limit)
    cutoff = db.now() - int(stale_after or TUNE.stale_after)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE manual = 0 AND (fails >= ? OR (checked_at < ? AND ok = 0))",
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

    Manual rows are exempt from the *deletion*, not from the floor: they are
    sidelined by ``drop`` and filtered out by ``pool``, so an unhealthy pinned
    endpoint is never handed to a user, it is just still visible to the admin who
    pinned it. An untested manual row (``latency = 0``) would otherwise be
    deleted here the moment the agent ran.
    """
    await ensure_schema()
    ceiling = TUNE.health_floor if floor is None else int(floor)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE manual = 0 "
        "AND (health < ? OR latency <= 0 OR verified = 0)",
        (ceiling,),
    )
    removed = int(cursor.rowcount or 0)
    await cursor.close()
    await db.conn().commit()
    return max(0, removed)


async def trim(keep: int, family: Optional[str] = None) -> int:
    """Cap a pool. Pinned rows first, then proven, then healthier, then faster.

    A manual row is never trimmed away. The cap exists to stop a scanner filling
    the table for ever, and applying it to endpoints an admin typed in by hand is
    how the IPv6 list somebody just entered disappears an hour later.
    """
    await ensure_schema()
    limit = max(2, int(keep))
    if family is None:
        await db.execute(
            f"DELETE FROM {TABLE} WHERE manual = 0 AND rowid NOT IN ("
            f"  SELECT rowid FROM {TABLE} "
            "   ORDER BY manual DESC, stable DESC, fails ASC, score ASC LIMIT ?)",
            (limit,),
        )
        return 0
    code = warpep.normalise_family(family)
    cursor = await db.conn().execute(
        f"DELETE FROM {TABLE} WHERE family = ? AND manual = 0 AND rowid NOT IN ("
        f"  SELECT rowid FROM {TABLE} WHERE family = ? "
        "   ORDER BY manual DESC, verified DESC, health DESC, latency ASC LIMIT ?)",
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

    Manual rows sit in here on exactly the same terms as scanned ones. An
    untested one has no ping to sort by, so it goes last: if a measured endpoint
    exists, that is what the user gets.
    """
    await ensure_schema()
    code = warpep.normalise_family(family)
    return [
        dict(row)
        for row in await db.fetch_all(
            f"SELECT {FIELDS} FROM {TABLE} "
            "WHERE family = ? AND stable = 1 AND fails = 0 AND health >= ? AND verified <> 0 "
            f"ORDER BY {BY_PING} LIMIT ?",
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


async def manual_rows(family: Optional[str] = None, limit: int = 60) -> list[dict]:
    """The endpoints an admin pinned, best first, dead ones last."""
    await ensure_schema()
    if family is None:
        return [
            dict(row)
            for row in await db.fetch_all(
                f"SELECT {FIELDS} FROM {TABLE} WHERE manual = 1 "
                f"ORDER BY family ASC, stable DESC, {BY_PING} LIMIT ?",
                (max(1, int(limit)),),
            )
        ]
    return [
        dict(row)
        for row in await db.fetch_all(
            f"SELECT {FIELDS} FROM {TABLE} WHERE manual = 1 AND family = ? "
            f"ORDER BY stable DESC, {BY_PING} LIMIT ?",
            (warpep.normalise_family(family), max(1, int(limit))),
        )
    ]


async def manual_counts(family: str) -> dict:
    """How many pinned endpoints one family has, and how many are usable."""
    await ensure_schema()
    code = warpep.normalise_family(family)
    floor = int(TUNE.health_floor)
    total = int(
        await db.scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE manual = 1 AND family = ?",
            (code,),
            default=0,
        )
        or 0
    )
    healthy = int(
        await db.scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE manual = 1 AND family = ? "
            "AND stable = 1 AND fails = 0 AND health >= ? AND verified <> 0",
            (code, floor),
            default=0,
        )
        or 0
    )
    measured = int(
        await db.scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE manual = 1 AND family = ? AND latency > 0",
            (code,),
            default=0,
        )
        or 0
    )
    return {
        "family": code,
        "total": total,
        "healthy": healthy,
        "measured": measured,
        "untested": max(0, total - measured),
        "dead": max(0, total - healthy),
    }


async def counts(family: str) -> dict:
    """How full one pool is, and how good the top of it is."""
    await ensure_schema()
    code = warpep.normalise_family(family)
    top = await db.fetch_one(
        f"SELECT ip, port, latency, health, verified FROM {TABLE} "
        f"WHERE family = ? AND stable = 1 AND fails = 0 ORDER BY {BY_PING} LIMIT 1",
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
    manual = int(
        await db.scalar(
            f"SELECT COUNT(*) FROM {TABLE} WHERE family = ? AND manual = 1",
            (code,),
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
        "manual": manual,
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
                    "WHERE family = ? AND stable = 1 AND fails = 0 AND latency > 0",
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
        "manual": int(
            await db.scalar(f"SELECT COUNT(*) FROM {TABLE} WHERE manual = 1", default=0) or 0
        ),
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
