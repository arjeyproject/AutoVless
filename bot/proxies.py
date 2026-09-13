"""Storage for verified proxyIP relays.

A relay is any non-Cloudflare host that forwards TCP to the Cloudflare edge.
Workers cannot open a socket to a Cloudflare-owned address, so without one of
these every destination that sits behind Cloudflare is unreachable and the
tunnel looks dead to the client.

Relays are reaped, not just demoted. A host that has stopped forwarding is worse
than no host at all: it sits at the head of a panel's failover chain and every
session pays its timeout before moving on.

Since 2.0 a relay also carries *where it exits*. That is not cosmetic: the relay
an AI destination leaves through decides which country Google, OpenAI and
Anthropic think the user is in, and a relay in the wrong country turns "it works"
into a region error. The column is filled lazily by ``ensure_countries`` rather
than by the scanner, so a sweep stays as fast as it was.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional, Sequence

from . import db, geoip
from .config import settings

log = logging.getLogger("autovless.proxies")

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
CREATE INDEX IF NOT EXISTS idx_proxy_recheck ON proxy_ips (checked_at ASC);
"""

# Added after 1.0. Existing databases are patched in place, exactly like db.py
# does for its own tables.
COLUMNS: dict[str, str] = {
    "exit_ip": "TEXT",
    "country": "TEXT",
    "isp": "TEXT",
    "hosting": "INTEGER NOT NULL DEFAULT 0",
    "geo_at": "INTEGER NOT NULL DEFAULT 0",
}

_ready = False


async def ensure() -> None:
    global _ready
    if _ready:
        return
    await db.conn().executescript(SCHEMA)
    async with db.conn().execute("PRAGMA table_info(proxy_ips)") as cur:
        present = {row[1] for row in await cur.fetchall()}
    for name, ddl in COLUMNS.items():
        if name not in present:
            await db.conn().execute(f"ALTER TABLE proxy_ips ADD COLUMN {name} {ddl}")
    await db.conn().execute(
        "CREATE INDEX IF NOT EXISTS idx_proxy_country ON proxy_ips (country, verified, fails, latency)"
    )
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


def _clause(countries: Sequence[str]) -> tuple[str, list]:
    codes = [str(code).strip().upper()[:2] for code in countries if str(code or "").strip()]
    if not codes:
        return "", []
    marks = ",".join("?" for _ in codes)
    return f"AND UPPER(COALESCE(country, '')) IN ({marks}) ", codes


async def best(
    limit: int,
    verified_only: bool = True,
    countries: Sequence[str] = (),
) -> list[dict]:
    """Fastest usable relays, optionally restricted to a set of exit countries."""
    await ensure()
    where, params = _clause(countries)
    sql = (
        "SELECT host, port, latency, colo, country, exit_ip, isp, hosting FROM proxy_ips "
        "WHERE fails < ? "
        + ("AND verified = 1 " if verified_only else "")
        + where
        + "ORDER BY latency ASC LIMIT ?"
    )
    rows = await db.fetch_all(sql, (settings.relay_strikes, *params, limit))
    return [dict(row) for row in rows]


async def alive(host: str, port: int = 443) -> Optional[dict]:
    """The stored row for one relay, only while it is still usable."""
    await ensure()
    row = await db.fetch_one(
        "SELECT host, port, latency, colo, country, exit_ip, isp, verified, fails "
        "FROM proxy_ips WHERE host = ? AND port = ? AND fails < ?",
        (str(host), int(port), settings.relay_strikes),
    )
    return dict(row) if row is not None else None


async def due_for_recheck(limit: int, max_age: int) -> list[dict]:
    """Relays nobody has confirmed lately, staleest first."""
    await ensure()
    cutoff = db.now() - max(60, max_age)
    rows = await db.fetch_all(
        "SELECT host, port, latency, colo, verified, fails, checked_at FROM proxy_ips "
        "WHERE checked_at <= ? ORDER BY verified DESC, checked_at ASC LIMIT ?",
        (cutoff, limit),
    )
    return [dict(row) for row in rows]


async def record_fail(host: str, port: int = 443) -> bool:
    """Count a miss and delete the relay once it has run out of chances.

    Returns True when the row was removed.
    """
    await ensure()
    await db.execute(
        "UPDATE proxy_ips SET fails = fails + 1, verified = 0, checked_at = ? "
        "WHERE host = ? AND port = ?",
        (db.now(), host, int(port)),
    )
    row = await db.fetch_one(
        "SELECT fails FROM proxy_ips WHERE host = ? AND port = ?", (host, int(port))
    )
    if row is None or int(row["fails"]) < settings.relay_strikes:
        return False
    await db.execute(
        "DELETE FROM proxy_ips WHERE host = ? AND port = ?", (host, int(port))
    )
    return True


async def mark_fail(host: str, port: int = 443) -> bool:
    """Kept for every existing caller; now reaps as well as demotes."""
    return await record_fail(host, port)


async def count(verified_only: bool = True) -> int:
    await ensure()
    sql = "SELECT COUNT(*) FROM proxy_ips WHERE fails < ?" + (
        " AND verified = 1" if verified_only else ""
    )
    return int(await db.scalar(sql, (settings.relay_strikes,)))


async def trim(keep: int) -> None:
    await ensure()
    await db.execute(
        "DELETE FROM proxy_ips WHERE rowid NOT IN "
        "(SELECT rowid FROM proxy_ips ORDER BY verified DESC, fails ASC, latency ASC LIMIT ?)",
        (keep,),
    )


# --------------------------------------------------------------------- #
# geolocation
# --------------------------------------------------------------------- #

GEO_TTL = 7 * 86_400


async def ensure_countries(hosts: Iterable[str], force: bool = False) -> dict[str, dict]:
    """Fill in the exit country for any of these relays we do not know yet.

    Called from the deploy path, where the answer is about to matter, and from
    the admin AI screen. Everything it learns is written back to the row, so a
    relay is looked up once a week at most however often it is picked.
    """
    await ensure()
    wanted = [str(host).strip() for host in hosts if str(host or "").strip()]
    if not wanted:
        return {}

    known: dict[str, dict] = {}
    unknown: list[str] = []
    cutoff = db.now() - GEO_TTL
    for host in dict.fromkeys(wanted):
        row = await db.fetch_one(
            "SELECT host, country, exit_ip, isp, geo_at FROM proxy_ips WHERE host = ? LIMIT 1",
            (host,),
        )
        if (
            not force
            and row is not None
            and row["country"]
            and int(row["geo_at"] or 0) >= cutoff
        ):
            known[host] = dict(row)
        else:
            unknown.append(host)

    if not unknown:
        return known

    try:
        found = await geoip.locate(unknown)
    except Exception:  # noqa: BLE001
        log.debug("geolocation failed", exc_info=True)
        found = {}

    ts = db.now()
    for host, row in found.items():
        await db.execute(
            "UPDATE proxy_ips SET country = ?, exit_ip = ?, isp = ?, hosting = ?, geo_at = ? "
            "WHERE host = ?",
            (row["country"], row["ip"], row["isp"], 1 if row.get("hosting") else 0, ts, host),
        )
        known[host] = {
            "host": host,
            "country": row["country"],
            "exit_ip": row["ip"],
            "isp": row["isp"],
            "geo_at": ts,
        }
    return known


async def country_counts(limit: int = 8) -> list[tuple[str, int]]:
    await ensure()
    rows = await db.fetch_all(
        "SELECT UPPER(country) AS code, COUNT(*) AS hits FROM proxy_ips "
        "WHERE verified = 1 AND country IS NOT NULL AND country != '' "
        "GROUP BY UPPER(country) ORDER BY hits DESC LIMIT ?",
        (limit,),
    )
    return [(str(row["code"]), int(row["hits"])) for row in rows]


async def stats() -> dict:
    await ensure()
    total = await db.scalar("SELECT COUNT(*) FROM proxy_ips")
    verified = await db.scalar("SELECT COUNT(*) FROM proxy_ips WHERE verified = 1")
    best_ms: Optional[float] = await db.scalar(
        "SELECT MIN(latency) FROM proxy_ips WHERE verified = 1", default=None
    )
    updated = await db.scalar("SELECT MAX(checked_at) FROM proxy_ips", default=0)
    placed = await db.scalar(
        "SELECT COUNT(*) FROM proxy_ips WHERE verified = 1 AND country IS NOT NULL AND country != ''"
    )
    american = await db.scalar(
        "SELECT COUNT(*) FROM proxy_ips WHERE verified = 1 AND UPPER(COALESCE(country, '')) = 'US'"
    )
    return {
        "total": int(total),
        "verified": int(verified),
        "best": round(float(best_ms), 1) if best_ms is not None else None,
        "updated_at": int(updated or 0),
        "placed": int(placed),
        "us": int(american),
        "countries": await country_counts(),
    }
