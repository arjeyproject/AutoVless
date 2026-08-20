"""Storage for verified proxyIP relays.

A relay is any non-Cloudflare host that forwards TCP to the Cloudflare edge.
Workers cannot open a socket to a Cloudflare-owned address, so without one of
these every destination that sits behind Cloudflare is unreachable and the
tunnel looks dead to the client.
"""

from __future__ import annotations

from typing import Optional

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS proxy_ips (
    host       TEXT    NOT NULL,
    port       INTEGER NOT NULL DEFAULT 443,
    latency    REAL    NOT NULL DEFAULT 0,
    colo       TEXT,
    verified   INTEGER NOT NULL DEFAULT 0,
    fails      INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (host, port)
);
CREATE INDEX IF NOT EXISTS idx_proxy_latency ON proxy_ips (verified, fails, latency);
"""

_ready = False


async def ensure() -> None:
    global _ready
    if _ready:
        return
    await db.conn().executescript(SCHEMA)
    await db.conn().commit()
    _ready = True


async def store(rows: list[dict]) -> None:
    if not rows:
        return
    await ensure()
    ts = db.now()
    payload = [
        (
            row["host"],
            int(row.get("port") or 443),
            float(row.get("latency") or 0),
            row.get("colo"),
            1 if row.get("verified") else 0,
            ts,
        )
        for row in rows
    ]
    await db.conn().executemany(
        "INSERT INTO proxy_ips (host, port, latency, colo, verified, fails, checked_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?) "
        "ON CONFLICT(host, port) DO UPDATE SET "
        "latency = excluded.latency, colo = COALESCE(excluded.colo, proxy_ips.colo), "
        "verified = excluded.verified, fails = 0, checked_at = excluded.checked_at",
        payload,
    )
    await db.conn().commit()


async def best(limit: int, verified_only: bool = True) -> list[dict]:
    await ensure()
    sql = (
        "SELECT host, port, latency, colo FROM proxy_ips WHERE fails < 3 "
        + ("AND verified = 1 " if verified_only else "")
        + "ORDER BY latency ASC LIMIT ?"
    )
    return [dict(row) for row in await db.fetch_all(sql, (limit,))]


async def mark_fail(host: str, port: int = 443) -> None:
    await ensure()
    await db.execute(
        "UPDATE proxy_ips SET fails = fails + 1 WHERE host = ? AND port = ?", (host, port)
    )


async def trim(keep: int) -> None:
    await ensure()
    await db.execute(
        "DELETE FROM proxy_ips WHERE rowid NOT IN "
        "(SELECT rowid FROM proxy_ips ORDER BY verified DESC, fails ASC, latency ASC LIMIT ?)",
        (keep,),
    )


async def stats() -> dict:
    await ensure()
    total = await db.scalar("SELECT COUNT(*) FROM proxy_ips")
    verified = await db.scalar("SELECT COUNT(*) FROM proxy_ips WHERE verified = 1")
    best_ms: Optional[float] = await db.scalar(
        "SELECT MIN(latency) FROM proxy_ips WHERE verified = 1", default=None
    )
    updated = await db.scalar("SELECT MAX(checked_at) FROM proxy_ips", default=0)
    return {
        "total": int(total),
        "verified": int(verified),
        "best": round(float(best_ms), 1) if best_ms is not None else None,
        "updated_at": int(updated or 0),
    }
