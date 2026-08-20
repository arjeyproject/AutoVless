"""SQLite storage layer. One shared connection, WAL mode, no ORM."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any, Optional, Sequence

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_conn: Optional[aiosqlite.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    lang       TEXT    NOT NULL DEFAULT 'fa',
    operator   TEXT,
    is_banned  INTEGER NOT NULL DEFAULT 0,
    builds     INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    seen_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS panels (
    tg_id       INTEGER PRIMARY KEY,
    account_id  TEXT    NOT NULL,
    script_name TEXT    NOT NULL,
    host        TEXT    NOT NULL,
    uuid        TEXT    NOT NULL,
    token_enc   TEXT,
    endpoints   TEXT    NOT NULL DEFAULT '[]',
    build_ms    INTEGER NOT NULL DEFAULT 0,
    rebuilds    INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    chat_id  TEXT PRIMARY KEY,
    title    TEXT,
    invite   TEXT,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clean_ips (
    ip         TEXT    NOT NULL,
    port       INTEGER NOT NULL,
    latency    REAL    NOT NULL,
    colo       TEXT,
    verified   INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL,
    PRIMARY KEY (ip, port)
);

CREATE TABLE IF NOT EXISTS warp_endpoints (
    ip         TEXT    NOT NULL,
    port       INTEGER NOT NULL,
    latency    REAL    NOT NULL,
    stable     INTEGER NOT NULL DEFAULT 0,
    checked_at INTEGER NOT NULL,
    PRIMARY KEY (ip, port)
);

CREATE TABLE IF NOT EXISTS warp_users (
    tg_id        INTEGER PRIMARY KEY,
    identity_enc TEXT    NOT NULL,
    endpoints    TEXT    NOT NULL DEFAULT '[]',
    account_type TEXT    NOT NULL DEFAULT 'free',
    refreshes    INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS options (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id   INTEGER,
    kind    TEXT NOT NULL,
    detail  TEXT,
    at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'open',
    unread_admin INTEGER NOT NULL DEFAULT 0,
    unread_user  INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    sender    TEXT    NOT NULL,
    admin_id  INTEGER,
    body      TEXT    NOT NULL,
    at        INTEGER NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_clean_latency ON clean_ips (port, verified, latency);
CREATE INDEX IF NOT EXISTS idx_warp_latency ON warp_endpoints (stable, latency);
CREATE INDEX IF NOT EXISTS idx_events_at ON events (at DESC);
CREATE INDEX IF NOT EXISTS idx_users_seen ON users (seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (tg_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_messages ON ticket_messages (ticket_id, id);
"""


def now() -> int:
    return int(time.time())


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> Optional[str]:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, AttributeError):
        return None


async def init() -> None:
    global _conn
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(settings.db_path)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA synchronous=NORMAL")
    await _conn.execute("PRAGMA foreign_keys=ON")
    await _conn.executescript(SCHEMA)
    await _conn.commit()


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("database is not initialised; call db.init() first")
    return _conn


async def fetch_one(sql: str, params: Sequence[Any] = ()) -> Optional[aiosqlite.Row]:
    async with conn().execute(sql, params) as cur:
        return await cur.fetchone()


async def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
    async with conn().execute(sql, params) as cur:
        return list(await cur.fetchall())


async def execute(sql: str, params: Sequence[Any] = ()) -> None:
    await conn().execute(sql, params)
    await conn().commit()


async def insert(sql: str, params: Sequence[Any] = ()) -> int:
    """Insert a row and return its new rowid."""
    cursor = await conn().execute(sql, params)
    await conn().commit()
    new_id = int(cursor.lastrowid or 0)
    await cursor.close()
    return new_id


async def scalar(sql: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
    row = await fetch_one(sql, params)
    if row is None or row[0] is None:
        return default
    return row[0]


# --------------------------------------------------------------------- #
# options
# --------------------------------------------------------------------- #

DEFAULT_OPTIONS: dict[str, str] = {
    "maintenance": "0",
    "builds_enabled": "1",
    "force_join": "1",
    "support_enabled": "1",
    "warp_enabled": "1",
    "welcome_extra": "",
    "support_note": "",
}


async def get_option(key: str, default: Optional[str] = None) -> str:
    row = await fetch_one("SELECT value FROM options WHERE key = ?", (key,))
    if row is not None:
        return row["value"]
    if default is not None:
        return default
    return DEFAULT_OPTIONS.get(key, "")


async def set_option(key: str, value: str) -> None:
    await execute(
        "INSERT INTO options (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def get_flag(key: str) -> bool:
    return (await get_option(key)).strip() in {"1", "true", "yes", "on"}


async def toggle_flag(key: str) -> bool:
    new_value = not await get_flag(key)
    await set_option(key, "1" if new_value else "0")
    return new_value


# --------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------- #


async def upsert_user(tg_id: int, username: Optional[str], first_name: Optional[str]) -> aiosqlite.Row:
    ts = now()
    await execute(
        """
        INSERT INTO users (tg_id, username, first_name, lang, created_at, seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
            username   = excluded.username,
            first_name = excluded.first_name,
            seen_at    = excluded.seen_at
        """,
        (tg_id, username, first_name, settings.default_lang, ts, ts),
    )
    row = await fetch_one("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    assert row is not None
    return row


async def get_user(tg_id: int) -> Optional[aiosqlite.Row]:
    return await fetch_one("SELECT * FROM users WHERE tg_id = ?", (tg_id,))


async def set_lang(tg_id: int, lang: str) -> None:
    await execute("UPDATE users SET lang = ? WHERE tg_id = ?", (lang, tg_id))


async def set_operator(tg_id: int, operator: Optional[str]) -> None:
    await execute("UPDATE users SET operator = ? WHERE tg_id = ?", (operator, tg_id))


async def set_banned(tg_id: int, banned: bool) -> None:
    await execute("UPDATE users SET is_banned = ? WHERE tg_id = ?", (1 if banned else 0, tg_id))


async def all_user_ids(include_banned: bool = False) -> list[int]:
    sql = "SELECT tg_id FROM users" if include_banned else "SELECT tg_id FROM users WHERE is_banned = 0"
    return [row["tg_id"] for row in await fetch_all(sql)]


async def find_users(term: str, limit: int = 15) -> list[aiosqlite.Row]:
    term = term.strip().lstrip("@")
    if term.isdigit():
        return await fetch_all("SELECT * FROM users WHERE tg_id = ?", (int(term),))
    like = f"%{term.lower()}%"
    return await fetch_all(
        "SELECT * FROM users WHERE LOWER(COALESCE(username, '')) LIKE ? "
        "OR LOWER(COALESCE(first_name, '')) LIKE ? ORDER BY seen_at DESC LIMIT ?",
        (like, like, limit),
    )


# --------------------------------------------------------------------- #
# panels
# --------------------------------------------------------------------- #


async def save_panel(
    tg_id: int,
    account_id: str,
    script_name: str,
    host: str,
    uuid: str,
    token: Optional[str],
    endpoints: list[dict],
    build_ms: int,
) -> None:
    ts = now()
    token_enc = encrypt(token) if (token and settings.store_tokens) else None
    await execute(
        """
        INSERT INTO panels (tg_id, account_id, script_name, host, uuid, token_enc,
                            endpoints, build_ms, rebuilds, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
            account_id  = excluded.account_id,
            script_name = excluded.script_name,
            host        = excluded.host,
            uuid        = excluded.uuid,
            token_enc   = COALESCE(excluded.token_enc, panels.token_enc),
            endpoints   = excluded.endpoints,
            build_ms    = excluded.build_ms,
            rebuilds    = panels.rebuilds + 1,
            updated_at  = excluded.updated_at
        """,
        (tg_id, account_id, script_name, host, uuid, token_enc,
         json.dumps(endpoints, ensure_ascii=False), build_ms, ts, ts),
    )
    await execute("UPDATE users SET builds = builds + 1 WHERE tg_id = ?", (tg_id,))


async def get_panel(tg_id: int) -> Optional[dict]:
    row = await fetch_one("SELECT * FROM panels WHERE tg_id = ?", (tg_id,))
    if row is None:
        return None
    panel = dict(row)
    panel["endpoints"] = json.loads(panel.get("endpoints") or "[]")
    panel["token"] = decrypt(panel["token_enc"]) if panel.get("token_enc") else None
    return panel


async def delete_panel(tg_id: int) -> None:
    await execute("DELETE FROM panels WHERE tg_id = ?", (tg_id,))


async def update_panel_endpoints(tg_id: int, endpoints: list[dict], build_ms: int) -> None:
    await execute(
        "UPDATE panels SET endpoints = ?, build_ms = ?, rebuilds = rebuilds + 1, updated_at = ? WHERE tg_id = ?",
        (json.dumps(endpoints, ensure_ascii=False), build_ms, now(), tg_id),
    )


# --------------------------------------------------------------------- #
# channels
# --------------------------------------------------------------------- #


async def add_channel(chat_id: str, title: str, invite: str) -> None:
    await execute(
        "INSERT INTO channels (chat_id, title, invite, added_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, invite = excluded.invite",
        (chat_id, title, invite, now()),
    )


async def remove_channel(chat_id: str) -> None:
    await execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))


async def channels() -> list[dict]:
    return [dict(row) for row in await fetch_all("SELECT * FROM channels ORDER BY added_at")]


# --------------------------------------------------------------------- #
# support tickets
# --------------------------------------------------------------------- #

TICKET_OPEN = "open"
TICKET_ANSWERED = "answered"
TICKET_CLOSED = "closed"

SENDER_USER = "user"
SENDER_ADMIN = "admin"

_TICKET_SELECT = (
    "SELECT t.*, u.username AS username, u.first_name AS first_name, u.lang AS user_lang "
    "FROM tickets t LEFT JOIN users u ON u.tg_id = t.tg_id "
)


async def open_ticket(tg_id: int) -> int:
    """Reuse the caller's live thread, or start a fresh one."""
    row = await fetch_one(
        "SELECT id FROM tickets WHERE tg_id = ? AND status != ? ORDER BY id DESC LIMIT 1",
        (tg_id, TICKET_CLOSED),
    )
    if row is not None:
        return int(row["id"])
    ts = now()
    return await insert(
        "INSERT INTO tickets (tg_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (tg_id, TICKET_OPEN, ts, ts),
    )


async def add_ticket_message(
    ticket_id: int,
    sender: str,
    body: str,
    admin_id: Optional[int] = None,
) -> None:
    ts = now()
    await execute(
        "INSERT INTO ticket_messages (ticket_id, sender, admin_id, body, at) VALUES (?, ?, ?, ?, ?)",
        (ticket_id, sender, admin_id, body[:4000], ts),
    )
    if sender == SENDER_ADMIN:
        await execute(
            "UPDATE tickets SET status = ?, updated_at = ?, unread_admin = 0, "
            "unread_user = unread_user + 1 WHERE id = ?",
            (TICKET_ANSWERED, ts, ticket_id),
        )
    else:
        await execute(
            "UPDATE tickets SET status = ?, updated_at = ?, unread_admin = unread_admin + 1 WHERE id = ?",
            (TICKET_OPEN, ts, ticket_id),
        )


async def get_ticket(ticket_id: int) -> Optional[dict]:
    row = await fetch_one(_TICKET_SELECT + "WHERE t.id = ?", (ticket_id,))
    return dict(row) if row is not None else None


async def latest_ticket(tg_id: int) -> Optional[dict]:
    row = await fetch_one(_TICKET_SELECT + "WHERE t.tg_id = ? ORDER BY t.id DESC LIMIT 1", (tg_id,))
    return dict(row) if row is not None else None


async def ticket_thread(ticket_id: int, limit: int = 12) -> list[dict]:
    rows = await fetch_all(
        "SELECT * FROM (SELECT * FROM ticket_messages WHERE ticket_id = ? "
        "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
        (ticket_id, limit),
    )
    return [dict(row) for row in rows]


async def ticket_message_count(ticket_id: int) -> int:
    return int(await scalar("SELECT COUNT(*) FROM ticket_messages WHERE ticket_id = ?", (ticket_id,)))


async def set_ticket_status(ticket_id: int, status: str) -> None:
    await execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), ticket_id),
    )


async def mark_ticket_seen(ticket_id: int, by: str) -> None:
    column = "unread_admin" if by == SENDER_ADMIN else "unread_user"
    await execute(f"UPDATE tickets SET {column} = 0 WHERE id = ?", (ticket_id,))


async def tickets(scope: str = "open", limit: int = 12) -> list[dict]:
    """Newest first, with anything waiting on the admin floated to the top."""
    where = "" if scope == "all" else f"WHERE t.status != '{TICKET_CLOSED}' "
    rows = await fetch_all(
        _TICKET_SELECT + where + "ORDER BY t.unread_admin DESC, t.updated_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


async def ticket_stats() -> dict:
    return {
        "open": int(await scalar("SELECT COUNT(*) FROM tickets WHERE status = ?", (TICKET_OPEN,))),
        "answered": int(await scalar("SELECT COUNT(*) FROM tickets WHERE status = ?", (TICKET_ANSWERED,))),
        "closed": int(await scalar("SELECT COUNT(*) FROM tickets WHERE status = ?", (TICKET_CLOSED,))),
        "waiting": int(await scalar("SELECT COUNT(*) FROM tickets WHERE unread_admin > 0")),
    }


async def last_support_message_at(tg_id: int) -> int:
    return int(
        await scalar(
            "SELECT MAX(m.at) FROM ticket_messages m JOIN tickets t ON t.id = m.ticket_id "
            "WHERE t.tg_id = ? AND m.sender = ?",
            (tg_id, SENDER_USER),
            default=0,
        )
        or 0
    )


# --------------------------------------------------------------------- #
# clean ip pool
# --------------------------------------------------------------------- #


async def store_clean_ips(rows: list[dict]) -> None:
    if not rows:
        return
    ts = now()
    payload = [
        (r["ip"], int(r["port"]), float(r["latency"]), r.get("colo"), 1 if r.get("verified") else 0, ts)
        for r in rows
    ]
    await conn().executemany(
        "INSERT INTO clean_ips (ip, port, latency, colo, verified, checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(ip, port) DO UPDATE SET "
        "latency = excluded.latency, colo = COALESCE(excluded.colo, clean_ips.colo), "
        "verified = excluded.verified, checked_at = excluded.checked_at",
        payload,
    )
    await conn().commit()


async def best_ips(port: int, limit: int, verified_only: bool = True) -> list[dict]:
    sql = (
        "SELECT ip, port, latency, colo FROM clean_ips WHERE port = ? "
        + ("AND verified = 1 " if verified_only else "")
        + "ORDER BY latency ASC LIMIT ?"
    )
    return [dict(row) for row in await fetch_all(sql, (port, limit))]


async def trim_pool(keep: int) -> None:
    await execute(
        "DELETE FROM clean_ips WHERE rowid NOT IN "
        "(SELECT rowid FROM clean_ips ORDER BY verified DESC, latency ASC LIMIT ?)",
        (keep,),
    )


async def pool_stats() -> dict:
    total = await scalar("SELECT COUNT(*) FROM clean_ips")
    verified = await scalar("SELECT COUNT(*) FROM clean_ips WHERE verified = 1")
    fast = await scalar("SELECT COUNT(*) FROM clean_ips WHERE latency < 700")
    best = await scalar("SELECT MIN(latency) FROM clean_ips WHERE verified = 1", default=None)
    updated = await scalar("SELECT MAX(checked_at) FROM clean_ips", default=0)
    return {
        "total": int(total),
        "verified": int(verified),
        "fast": int(fast),
        "best": round(float(best), 1) if best is not None else None,
        "updated_at": int(updated or 0),
    }


# --------------------------------------------------------------------- #
# warp endpoint pool
# --------------------------------------------------------------------- #


async def store_warp_endpoints(rows: list[dict]) -> None:
    if not rows:
        return
    ts = now()
    payload = [
        (r["ip"], int(r["port"]), float(r["latency"]), 1 if r.get("stable") else 0, ts)
        for r in rows
    ]
    await conn().executemany(
        "INSERT INTO warp_endpoints (ip, port, latency, stable, checked_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(ip, port) DO UPDATE SET "
        "latency = excluded.latency, stable = excluded.stable, checked_at = excluded.checked_at",
        payload,
    )
    await conn().commit()


async def best_warp_endpoints(limit: int, stable_only: bool = True) -> list[dict]:
    sql = (
        "SELECT ip, port, latency, stable, checked_at FROM warp_endpoints "
        + ("WHERE stable = 1 " if stable_only else "")
        + "ORDER BY latency ASC LIMIT ?"
    )
    return [dict(row) for row in await fetch_all(sql, (limit,))]


async def trim_warp_pool(keep: int) -> None:
    await execute(
        "DELETE FROM warp_endpoints WHERE rowid NOT IN "
        "(SELECT rowid FROM warp_endpoints ORDER BY stable DESC, latency ASC LIMIT ?)",
        (keep,),
    )


async def warp_pool_stats() -> dict:
    total = await scalar("SELECT COUNT(*) FROM warp_endpoints")
    stable = await scalar("SELECT COUNT(*) FROM warp_endpoints WHERE stable = 1")
    fast = await scalar("SELECT COUNT(*) FROM warp_endpoints WHERE latency < 300")
    best = await scalar("SELECT MIN(latency) FROM warp_endpoints WHERE stable = 1", default=None)
    updated = await scalar("SELECT MAX(checked_at) FROM warp_endpoints", default=0)
    return {
        "total": int(total),
        "stable": int(stable),
        "fast": int(fast),
        "best": round(float(best), 1) if best is not None else None,
        "updated_at": int(updated or 0),
        "users": int(await scalar("SELECT COUNT(*) FROM warp_users")),
    }


# --------------------------------------------------------------------- #
# warp identities
# --------------------------------------------------------------------- #


async def save_warp_user(tg_id: int, identity: dict, endpoints: list[dict]) -> None:
    ts = now()
    blob = encrypt(json.dumps(identity, ensure_ascii=False))
    await execute(
        """
        INSERT INTO warp_users (tg_id, identity_enc, endpoints, account_type,
                                refreshes, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
            identity_enc = excluded.identity_enc,
            endpoints    = excluded.endpoints,
            account_type = excluded.account_type,
            refreshes    = warp_users.refreshes + 1,
            updated_at   = excluded.updated_at
        """,
        (
            tg_id,
            blob,
            json.dumps(endpoints, ensure_ascii=False),
            str(identity.get("account_type") or "free"),
            ts,
            ts,
        ),
    )


async def update_warp_endpoints(tg_id: int, endpoints: list[dict]) -> None:
    await execute(
        "UPDATE warp_users SET endpoints = ?, refreshes = refreshes + 1, updated_at = ? "
        "WHERE tg_id = ?",
        (json.dumps(endpoints, ensure_ascii=False), now(), tg_id),
    )


async def get_warp_user(tg_id: int) -> Optional[dict]:
    row = await fetch_one("SELECT * FROM warp_users WHERE tg_id = ?", (tg_id,))
    if row is None:
        return None
    record = dict(row)
    raw = decrypt(record.get("identity_enc") or "")
    if not raw:
        return None
    try:
        record["identity"] = json.loads(raw)
    except ValueError:
        return None
    try:
        record["endpoints"] = json.loads(record.get("endpoints") or "[]")
    except ValueError:
        record["endpoints"] = []
    return record


async def delete_warp_user(tg_id: int) -> None:
    await execute("DELETE FROM warp_users WHERE tg_id = ?", (tg_id,))


# --------------------------------------------------------------------- #
# events / stats
# --------------------------------------------------------------------- #


async def log_event(kind: str, tg_id: Optional[int] = None, detail: str = "") -> None:
    await execute(
        "INSERT INTO events (tg_id, kind, detail, at) VALUES (?, ?, ?, ?)",
        (tg_id, kind, detail[:500], now()),
    )


async def recent_events(limit: int = 15) -> list[dict]:
    return [dict(r) for r in await fetch_all("SELECT * FROM events ORDER BY at DESC LIMIT ?", (limit,))]


async def global_stats() -> dict:
    day = now() - 86_400
    week = now() - 7 * 86_400
    return {
        "users": int(await scalar("SELECT COUNT(*) FROM users")),
        "users_today": int(await scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", (day,))),
        "active_week": int(await scalar("SELECT COUNT(*) FROM users WHERE seen_at >= ?", (week,))),
        "banned": int(await scalar("SELECT COUNT(*) FROM users WHERE is_banned = 1")),
        "panels": int(await scalar("SELECT COUNT(*) FROM panels")),
        "panels_today": int(await scalar("SELECT COUNT(*) FROM panels WHERE created_at >= ?", (day,))),
        "rebuilds": int(await scalar("SELECT COALESCE(SUM(rebuilds), 0) FROM panels")),
        "avg_build_ms": int(await scalar("SELECT COALESCE(AVG(build_ms), 0) FROM panels")),
        "channels": int(await scalar("SELECT COUNT(*) FROM channels")),
        "tickets_waiting": int(await scalar("SELECT COUNT(*) FROM tickets WHERE unread_admin > 0")),
        "warp_users": int(await scalar("SELECT COUNT(*) FROM warp_users")),
    }
