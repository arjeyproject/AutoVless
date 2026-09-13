"""Tables added after 1.0: referrals, the free config pool, and the AI pin.

Kept out of ``db.py`` on purpose, the same way ``proxies.py`` keeps its own
schema: this module owns its DDL, patches it in place on first use, and an
existing database picks all of it up on the next boot with no migration step to
run by hand.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from . import db

log = logging.getLogger("autovless.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS referrals (
    invitee  INTEGER PRIMARY KEY,
    inviter  INTEGER NOT NULL,
    at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS free_servers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    host       TEXT    NOT NULL,
    uuid       TEXT    NOT NULL,
    password   TEXT,
    path       TEXT    NOT NULL DEFAULT '/?ed=2560',
    label      TEXT,
    source     TEXT    NOT NULL DEFAULT 'manual',
    active     INTEGER NOT NULL DEFAULT 1,
    healthy    INTEGER NOT NULL DEFAULT 0,
    hits       INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL DEFAULT 0,
    added_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS free_grants (
    tg_id     INTEGER NOT NULL,
    server_id INTEGER NOT NULL,
    protocol  TEXT    NOT NULL,
    count     INTEGER NOT NULL DEFAULT 1,
    at        INTEGER NOT NULL,
    PRIMARY KEY (tg_id, server_id, protocol)
);

CREATE TABLE IF NOT EXISTS ai_pins (
    uuid    TEXT PRIMARY KEY,
    relay   TEXT NOT NULL,
    country TEXT,
    at      INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_free_host ON free_servers (host, uuid);
CREATE INDEX IF NOT EXISTS idx_referrals_inviter ON referrals (inviter);
"""

# Columns newer releases expect on tables ``db.py`` owns.
EXTRA_COLUMNS: dict[str, dict[str, str]] = {
    "users": {"theme": "TEXT NOT NULL DEFAULT 'auto'"},
    "panels": {"ai_relay": "TEXT", "ai_country": "TEXT"},
}

DEFAULTS: dict[str, str] = {
    "referral_lock": "0",
    "referral_required": "3",
    "free_enabled": "1",
    "free_per_user": "0",
    "miniapp_enabled": "1",
}

_ready = False


async def ensure() -> None:
    global _ready
    if _ready:
        return
    await db.conn().executescript(SCHEMA)
    for table, columns in EXTRA_COLUMNS.items():
        async with db.conn().execute(f"PRAGMA table_info({table})") as cur:
            present = {row[1] for row in await cur.fetchall()}
        if not present:
            continue
        for name, ddl in columns.items():
            if name not in present:
                await db.conn().execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    await db.conn().commit()
    for key, value in DEFAULTS.items():
        row = await db.fetch_one("SELECT 1 FROM options WHERE key = ?", (key,))
        if row is None:
            await db.set_option(key, value)
    _ready = True


# --------------------------------------------------------------------- #
# options with a number in them
# --------------------------------------------------------------------- #


async def get_int(key: str, default: int = 0) -> int:
    await ensure()
    raw = await db.get_option(key, str(default))
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


async def set_int(key: str, value: int) -> None:
    await ensure()
    await db.set_option(key, str(int(value)))


async def flag(key: str, default: bool = False) -> bool:
    await ensure()
    raw = (await db.get_option(key, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------- #
# referrals
# --------------------------------------------------------------------- #


async def credit_referral(inviter: int, invitee: int) -> bool:
    """Record that ``invitee`` arrived through ``inviter``. True when it counted.

    Three things are refused, and each of them is somebody trying it on: crediting
    yourself, crediting an account that has been in the bot before, and crediting
    an invitee twice. The middle rule is the important one - without it a user
    with two Telegram accounts can unlock the bot forever.
    """
    await ensure()
    inviter = int(inviter)
    invitee = int(invitee)
    if inviter == invitee or inviter <= 0 or invitee <= 0:
        return False

    existing = await db.fetch_one("SELECT inviter FROM referrals WHERE invitee = ?", (invitee,))
    if existing is not None:
        return False

    row = await db.fetch_one("SELECT created_at, seen_at FROM users WHERE tg_id = ?", (invitee,))
    if row is not None and int(row["seen_at"] or 0) - int(row["created_at"] or 0) > 900:
        # Not a new arrival: this account has been using the bot for a while.
        return False

    if await db.fetch_one("SELECT 1 FROM users WHERE tg_id = ?", (inviter,)) is None:
        return False

    await db.execute(
        "INSERT OR IGNORE INTO referrals (invitee, inviter, at) VALUES (?, ?, ?)",
        (invitee, inviter, db.now()),
    )
    await db.log_event("referral", inviter, f"invited {invitee}")
    return True


async def referral_count(inviter: int) -> int:
    await ensure()
    return int(await db.scalar("SELECT COUNT(*) FROM referrals WHERE inviter = ?", (int(inviter),)))


async def inviter_of(invitee: int) -> Optional[int]:
    await ensure()
    row = await db.fetch_one("SELECT inviter FROM referrals WHERE invitee = ?", (int(invitee),))
    return int(row["inviter"]) if row is not None else None


async def referral_top(limit: int = 10) -> list[dict]:
    await ensure()
    rows = await db.fetch_all(
        "SELECT r.inviter AS tg_id, COUNT(*) AS invites, u.username, u.first_name "
        "FROM referrals r LEFT JOIN users u ON u.tg_id = r.inviter "
        "GROUP BY r.inviter ORDER BY invites DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


async def referral_stats() -> dict:
    await ensure()
    day = db.now() - 86_400
    return {
        "total": int(await db.scalar("SELECT COUNT(*) FROM referrals")),
        "today": int(await db.scalar("SELECT COUNT(*) FROM referrals WHERE at >= ?", (day,))),
        "inviters": int(await db.scalar("SELECT COUNT(DISTINCT inviter) FROM referrals")),
        "required": await get_int("referral_required", 3),
        "locked": await flag("referral_lock"),
    }


# --------------------------------------------------------------------- #
# free config pool
# --------------------------------------------------------------------- #


async def add_free_server(
    host: str,
    uuid: str,
    password: str = "",
    path: str = "/?ed=2560",
    label: str = "",
    source: str = "manual",
) -> int:
    await ensure()
    host = str(host).strip().lower().replace("https://", "").replace("http://", "").strip("/")
    uuid = str(uuid).strip().lower()
    if not host or not uuid:
        raise ValueError("host and uuid are required")
    await db.execute(
        "INSERT INTO free_servers (host, uuid, password, path, label, source, active, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?) "
        "ON CONFLICT(host, uuid) DO UPDATE SET "
        "password = excluded.password, path = excluded.path, label = excluded.label, "
        "source = excluded.source, active = 1",
        (host, uuid, password or uuid, path or "/?ed=2560", label or host, source, db.now()),
    )
    row = await db.fetch_one(
        "SELECT id FROM free_servers WHERE host = ? AND uuid = ?", (host, uuid)
    )
    return int(row["id"]) if row else 0


async def free_servers(active_only: bool = True) -> list[dict]:
    await ensure()
    sql = "SELECT * FROM free_servers " + ("WHERE active = 1 " if active_only else "")
    return [dict(row) for row in await db.fetch_all(sql + "ORDER BY healthy DESC, id ASC")]


async def free_server(server_id: int) -> Optional[dict]:
    await ensure()
    row = await db.fetch_one("SELECT * FROM free_servers WHERE id = ?", (int(server_id),))
    return dict(row) if row is not None else None


async def remove_free_server(server_id: int) -> None:
    await ensure()
    await db.execute("DELETE FROM free_servers WHERE id = ?", (int(server_id),))


async def toggle_free_server(server_id: int) -> bool:
    await ensure()
    row = await free_server(server_id)
    if row is None:
        return False
    state = 0 if int(row.get("active") or 0) else 1
    await db.execute("UPDATE free_servers SET active = ? WHERE id = ?", (state, int(server_id)))
    return bool(state)


async def mark_free_server(server_id: int, healthy: bool) -> None:
    await ensure()
    await db.execute(
        "UPDATE free_servers SET healthy = ?, checked_at = ? WHERE id = ?",
        (1 if healthy else 0, db.now(), int(server_id)),
    )


async def record_free_grant(tg_id: int, server_id: int, protocol: str) -> None:
    await ensure()
    await db.execute(
        "INSERT INTO free_grants (tg_id, server_id, protocol, count, at) VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(tg_id, server_id, protocol) DO UPDATE SET "
        "count = free_grants.count + 1, at = excluded.at",
        (int(tg_id), int(server_id), str(protocol)[:16], db.now()),
    )
    await db.execute("UPDATE free_servers SET hits = hits + 1 WHERE id = ?", (int(server_id),))


async def free_grants(tg_id: int) -> int:
    await ensure()
    return int(
        await db.scalar("SELECT COALESCE(SUM(count), 0) FROM free_grants WHERE tg_id = ?", (int(tg_id),))
    )


async def free_stats() -> dict:
    await ensure()
    return {
        "servers": int(await db.scalar("SELECT COUNT(*) FROM free_servers WHERE active = 1")),
        "healthy": int(await db.scalar("SELECT COUNT(*) FROM free_servers WHERE active = 1 AND healthy = 1")),
        "grants": int(await db.scalar("SELECT COALESCE(SUM(count), 0) FROM free_grants")),
        "users": int(await db.scalar("SELECT COUNT(DISTINCT tg_id) FROM free_grants")),
        "enabled": await flag("free_enabled", True),
    }


# --------------------------------------------------------------------- #
# the AI exit pin
# --------------------------------------------------------------------- #


async def ai_pin(uuid: str) -> Optional[dict]:
    await ensure()
    row = await db.fetch_one("SELECT * FROM ai_pins WHERE uuid = ?", (str(uuid),))
    return dict(row) if row is not None else None


async def set_ai_pin(uuid: str, relay: str, country: str = "") -> None:
    await ensure()
    await db.execute(
        "INSERT INTO ai_pins (uuid, relay, country, at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(uuid) DO UPDATE SET relay = excluded.relay, country = excluded.country, "
        "at = excluded.at",
        (str(uuid), str(relay), str(country or "").upper()[:2], db.now()),
    )


async def clear_ai_pin(uuid: str) -> None:
    await ensure()
    await db.execute("DELETE FROM ai_pins WHERE uuid = ?", (str(uuid),))


async def ai_pin_stats() -> dict:
    await ensure()
    rows = await db.fetch_all(
        "SELECT UPPER(COALESCE(country, '??')) AS code, COUNT(*) AS hits FROM ai_pins "
        "GROUP BY UPPER(COALESCE(country, '??')) ORDER BY hits DESC LIMIT 6"
    )
    return {
        "pinned": int(await db.scalar("SELECT COUNT(*) FROM ai_pins")),
        "countries": [(str(row["code"]), int(row["hits"])) for row in rows],
    }


# --------------------------------------------------------------------- #
# per-user mini app preferences
# --------------------------------------------------------------------- #


async def get_theme(tg_id: int) -> str:
    await ensure()
    row = await db.fetch_one("SELECT theme FROM users WHERE tg_id = ?", (int(tg_id),))
    theme = str((row["theme"] if row is not None else "") or "auto").lower()
    return theme if theme in {"auto", "dark", "light"} else "auto"


async def set_theme(tg_id: int, theme: str) -> None:
    await ensure()
    theme = str(theme or "auto").lower()
    if theme not in {"auto", "dark", "light"}:
        theme = "auto"
    await db.execute("UPDATE users SET theme = ? WHERE tg_id = ?", (theme, int(tg_id)))


def dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
