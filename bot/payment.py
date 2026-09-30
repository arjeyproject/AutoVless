"""Paid entry: an automatic payment gateway in front of the whole bot.

What the admin owns
-------------------
Everything here is configured from the bot's own admin panel and stored in the
``options`` table, so nothing needs an ``.env`` edit or a restart:

  * ``pay_enabled``   the paywall on or off
  * ``pay_gateway``   ``zarinpal``, ``stars`` or ``both``
  * ``pay_amount``    the price in Toman (Zarinpal)
  * ``pay_stars``     the price in Telegram Stars
  * ``pay_days``      how long one payment unlocks the bot, ``0`` for lifetime
  * ``pay_merchant``  the Zarinpal merchant id
  * ``pay_sandbox``   Zarinpal sandbox, for testing without real money

Two gateways, both fully automatic
---------------------------------
**Zarinpal** is the Iranian card gateway. The bot creates a payment, sends the
user to Zarinpal, and Zarinpal redirects back to ``/pay/zarinpal/callback`` on
the operator's own HTTPS domain (``PUBLIC_URL``). The callback verifies the
payment with Zarinpal server-to-server, using the amount stored here rather than
anything in the query string, and unlocks the user in the same request. The
verify step is idempotent, so a refreshed callback page never double-credits.

**Telegram Stars** needs no domain, no merchant and no callback at all: Telegram
itself collects the payment and delivers ``successful_payment`` to the bot. It is
the gateway to pick when the server has no domain yet.

Admins are never asked to pay.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Optional

import httpx

from . import db
from .config import settings

log = logging.getLogger("autovless.payment")

GATEWAYS: tuple[str, ...] = ("stars", "zarinpal", "both")

DEFAULTS: dict[str, str] = {
    "pay_enabled": "0",
    "pay_gateway": "stars",
    "pay_amount": "50000",
    "pay_stars": "100",
    "pay_days": "0",
    "pay_merchant": "",
    "pay_sandbox": "0",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id      INTEGER NOT NULL,
    gateway    TEXT    NOT NULL,
    amount     INTEGER NOT NULL,
    currency   TEXT    NOT NULL,
    authority  TEXT,
    ref_id     TEXT,
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    paid_at    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    tg_id      INTEGER PRIMARY KEY,
    paid_at    INTEGER NOT NULL,
    expires_at INTEGER NOT NULL DEFAULT 0,
    payments   INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_authority ON payments (authority);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (tg_id);
"""

ZP_LIVE = "https://payment.zarinpal.com"
ZP_SANDBOX = "https://sandbox.zarinpal.com"
# Zarinpal answers 100 for a fresh verification and 101 for one it has already
# verified. Both mean the money arrived.
ZP_OK = {100, 101}

_ready = False
_bot: Any = None


class PaymentError(Exception):
    """Raised with a message that is safe to show the user."""


# --------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------- #


def bind_bot(bot: Any) -> None:
    """The API has no Bot handle of its own; main.run() hands it over once."""
    global _bot
    _bot = bot


def bot() -> Any:
    return _bot


async def ensure() -> None:
    global _ready
    if _ready:
        return
    await db.conn().executescript(SCHEMA)
    await db.conn().commit()
    for key, value in DEFAULTS.items():
        if await db.fetch_one("SELECT 1 FROM options WHERE key = ?", (key,)) is None:
            await db.set_option(key, value)
    _ready = True


async def get(key: str) -> str:
    await ensure()
    return str(await db.get_option(key, DEFAULTS.get(key, "")) or "").strip()


async def get_int(key: str) -> int:
    raw = await get(key)
    try:
        return int(raw)
    except ValueError:
        return int(DEFAULTS.get(key, "0") or 0)


async def put(key: str, value: object) -> None:
    await ensure()
    await db.set_option(key, str(value))


async def flag(key: str) -> bool:
    return (await get(key)).lower() in {"1", "true", "yes", "on"}


async def toggle(key: str) -> bool:
    state = not await flag(key)
    await put(key, "1" if state else "0")
    return state


async def config() -> dict:
    gateway = (await get("pay_gateway")).lower()
    return {
        "enabled": await flag("pay_enabled"),
        "gateway": gateway if gateway in GATEWAYS else "stars",
        "amount": max(0, await get_int("pay_amount")),
        "stars": max(0, await get_int("pay_stars")),
        "days": max(0, await get_int("pay_days")),
        "merchant": await get("pay_merchant"),
        "sandbox": await flag("pay_sandbox"),
    }


def uses_zarinpal(cfg: dict) -> bool:
    return cfg["gateway"] in {"zarinpal", "both"} and bool(cfg["merchant"]) and cfg["amount"] > 0


def uses_stars(cfg: dict) -> bool:
    return cfg["gateway"] in {"stars", "both"} and cfg["stars"] > 0


async def enabled() -> bool:
    return await flag("pay_enabled")


# --------------------------------------------------------------------- #
# who has paid
# --------------------------------------------------------------------- #


async def subscription(tg_id: int) -> Optional[dict]:
    await ensure()
    row = await db.fetch_one("SELECT * FROM subscriptions WHERE tg_id = ?", (int(tg_id),))
    return dict(row) if row is not None else None


def _active(row: Optional[dict]) -> bool:
    if row is None:
        return False
    expires = int(row.get("expires_at") or 0)
    return expires == 0 or expires > int(time.time())


async def is_paid(tg_id: int, is_admin: bool = False) -> bool:
    """True when this user may use the bot. Admins and a disabled paywall pass."""
    if is_admin or settings.is_admin(int(tg_id)):
        return True
    if not await enabled():
        return True
    return _active(await subscription(tg_id))


async def grant(tg_id: int, days: Optional[int] = None) -> int:
    """Unlock a user. Returns the new expiry, ``0`` meaning lifetime.

    A timed payment extends from whichever is later, now or the current expiry,
    so paying early never throws away days somebody already bought.
    """
    await ensure()
    if days is None:
        days = await get_int("pay_days")
    days = max(0, int(days))
    now = int(time.time())
    current = await subscription(tg_id)

    if days == 0:
        expires = 0
    else:
        base = now
        if current is not None and int(current.get("expires_at") or 0) > now:
            base = int(current["expires_at"])
        expires = base + days * 86_400

    await db.execute(
        "INSERT INTO subscriptions (tg_id, paid_at, expires_at, payments) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(tg_id) DO UPDATE SET paid_at = excluded.paid_at, "
        "expires_at = excluded.expires_at, payments = subscriptions.payments + 1",
        (int(tg_id), now, expires),
    )
    return expires


async def revoke(tg_id: int) -> bool:
    await ensure()
    existed = await subscription(tg_id) is not None
    await db.execute("DELETE FROM subscriptions WHERE tg_id = ?", (int(tg_id),))
    return existed


async def _record(
    tg_id: int,
    gateway: str,
    amount: int,
    currency: str,
    authority: str = "",
    status: str = "pending",
    ref_id: str = "",
) -> int:
    await ensure()
    now = int(time.time())
    await db.execute(
        "INSERT INTO payments (tg_id, gateway, amount, currency, authority, ref_id, status, "
        "created_at, paid_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(tg_id),
            gateway,
            int(amount),
            currency,
            authority or None,
            ref_id or None,
            status,
            now,
            now if status == "paid" else 0,
        ),
    )
    row = await db.fetch_one("SELECT MAX(id) AS id FROM payments WHERE tg_id = ?", (int(tg_id),))
    return int(row["id"]) if row is not None and row["id"] is not None else 0


# --------------------------------------------------------------------- #
# zarinpal
# --------------------------------------------------------------------- #


def _zp_base(sandbox: bool) -> str:
    return ZP_SANDBOX if sandbox else ZP_LIVE


def callback_url() -> str:
    from . import subgw

    origin = subgw.origin()
    return f"{origin}/pay/zarinpal/callback" if origin else ""


async def zarinpal_start(tg_id: int, description: str = "") -> str:
    """Open a Zarinpal payment and return the URL the user has to visit."""
    cfg = await config()
    if not uses_zarinpal(cfg):
        raise PaymentError("zarinpal is not configured")
    callback = callback_url()
    if not callback.startswith("https://"):
        raise PaymentError("PUBLIC_URL (https) is not set on the server")

    # Zarinpal v4 takes Rial by default. The admin thinks in Toman.
    amount_rial = int(cfg["amount"]) * 10
    body = {
        "merchant_id": cfg["merchant"],
        "amount": amount_rial,
        "callback_url": callback,
        "description": (description or f"{settings.brand} #{tg_id}")[:250],
        "metadata": {"order_id": f"{tg_id}-{secrets.token_hex(4)}"},
    }
    base = _zp_base(cfg["sandbox"])
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{base}/pg/v4/payment/request.json",
                json=body,
                headers={"accept": "application/json", "content-type": "application/json"},
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        log.warning("zarinpal request failed: %s", error)
        raise PaymentError("the payment gateway did not answer") from error

    data = payload.get("data") if isinstance(payload, dict) else None
    authority = str((data or {}).get("authority") or "") if isinstance(data, dict) else ""
    code = int((data or {}).get("code") or 0) if isinstance(data, dict) else 0
    if code != 100 or not authority:
        errors = payload.get("errors") if isinstance(payload, dict) else None
        message = ""
        if isinstance(errors, dict):
            message = str(errors.get("message") or errors.get("code") or "")
        log.warning("zarinpal refused the request: %s", payload)
        raise PaymentError(message or "the payment gateway refused the request")

    await _record(tg_id, "zarinpal", amount_rial, "IRR", authority=authority)
    return f"{base}/pg/StartPay/{authority}"


async def zarinpal_verify(authority: str, status: str) -> dict:
    """Finish a Zarinpal payment. Safe to call any number of times."""
    await ensure()
    authority = str(authority or "").strip()
    row = await db.fetch_one("SELECT * FROM payments WHERE authority = ?", (authority,))
    if row is None:
        return {"ok": False, "reason": "unknown payment"}
    row = dict(row)
    tg_id = int(row["tg_id"])

    if row["status"] == "paid":
        return {"ok": True, "tg_id": tg_id, "ref": row.get("ref_id") or "", "again": True}

    if str(status or "").upper() != "OK":
        await db.execute("UPDATE payments SET status = 'failed' WHERE id = ?", (row["id"],))
        return {"ok": False, "tg_id": tg_id, "reason": "cancelled"}

    cfg = await config()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{_zp_base(cfg['sandbox'])}/pg/v4/payment/verify.json",
                json={
                    "merchant_id": cfg["merchant"],
                    "amount": int(row["amount"]),
                    "authority": authority,
                },
                headers={"accept": "application/json", "content-type": "application/json"},
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        log.warning("zarinpal verify failed: %s", error)
        return {"ok": False, "tg_id": tg_id, "reason": "gateway unreachable, retry"}

    data = payload.get("data") if isinstance(payload, dict) else None
    code = int((data or {}).get("code") or 0) if isinstance(data, dict) else 0
    if code not in ZP_OK:
        await db.execute("UPDATE payments SET status = 'failed' WHERE id = ?", (row["id"],))
        log.info("zarinpal verify refused %s: %s", authority, payload)
        return {"ok": False, "tg_id": tg_id, "reason": "not verified"}

    ref = str((data or {}).get("ref_id") or "")
    await db.execute(
        "UPDATE payments SET status = 'paid', ref_id = ?, paid_at = ? WHERE id = ?",
        (ref, int(time.time()), row["id"]),
    )
    expires = await grant(tg_id)
    await db.log_event("payment", tg_id, f"zarinpal ref={ref}")
    return {"ok": True, "tg_id": tg_id, "ref": ref, "expires": expires}


# --------------------------------------------------------------------- #
# telegram stars
# --------------------------------------------------------------------- #

STARS_PREFIX = "pay"


def stars_payload(tg_id: int) -> str:
    return f"{STARS_PREFIX}:{int(tg_id)}:{secrets.token_hex(4)}"


def payload_user(payload: str) -> Optional[int]:
    parts = str(payload or "").split(":")
    if len(parts) != 3 or parts[0] != STARS_PREFIX or not parts[1].isdigit():
        return None
    return int(parts[1])


async def stars_check(tg_id: int, payload: str, amount: int, currency: str) -> bool:
    """The pre-checkout gate: right user, right currency, right price."""
    if currency != "XTR" or payload_user(payload) != int(tg_id):
        return False
    cfg = await config()
    return uses_stars(cfg) and int(amount) == int(cfg["stars"])


async def stars_paid(tg_id: int, amount: int, charge_id: str) -> int:
    """Record a Stars payment Telegram has already settled, then unlock."""
    await ensure()
    existing = await db.fetch_one("SELECT id FROM payments WHERE authority = ?", (charge_id,))
    if existing is None:
        await _record(tg_id, "stars", amount, "XTR", authority=charge_id, status="paid", ref_id=charge_id)
    expires = await grant(tg_id)
    await db.log_event("payment", tg_id, f"stars {amount}")
    return expires


async def stars_invoice_link(title: str, description: str, label: str, tg_id: int) -> str:
    """An invoice link the mini app can open with ``Telegram.WebApp.openInvoice``."""
    from aiogram.types import LabeledPrice

    cfg = await config()
    if not uses_stars(cfg) or _bot is None:
        raise PaymentError("stars are not configured")
    return await _bot.create_invoice_link(
        title=title[:32],
        description=description[:255],
        payload=stars_payload(tg_id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=label[:32], amount=int(cfg["stars"]))],
    )


# --------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------- #


async def stats() -> dict:
    await ensure()
    now = int(time.time())
    return {
        "subscribers": int(await db.scalar("SELECT COUNT(*) FROM subscriptions")),
        "active": int(
            await db.scalar(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at = 0 OR expires_at > ?", (now,)
            )
        ),
        "toman": int(
            await db.scalar(
                "SELECT COALESCE(SUM(amount), 0) FROM payments "
                "WHERE status = 'paid' AND currency = 'IRR'"
            )
        )
        // 10,
        "stars": int(
            await db.scalar(
                "SELECT COALESCE(SUM(amount), 0) FROM payments "
                "WHERE status = 'paid' AND currency = 'XTR'"
            )
        ),
        "paid": int(await db.scalar("SELECT COUNT(*) FROM payments WHERE status = 'paid'")),
        "pending": int(await db.scalar("SELECT COUNT(*) FROM payments WHERE status = 'pending'")),
    }


async def recent(limit: int = 10) -> list[dict]:
    await ensure()
    rows = await db.fetch_all(
        "SELECT p.*, u.username, u.first_name FROM payments p "
        "LEFT JOIN users u ON u.tg_id = p.tg_id "
        "WHERE p.status = 'paid' ORDER BY p.paid_at DESC LIMIT ?",
        (int(limit),),
    )
    return [dict(row) for row in rows]


async def public_state(tg_id: int, is_admin: bool = False) -> dict:
    """What the mini app needs to draw the paywall. No secrets in here."""
    cfg = await config()
    row = await subscription(tg_id)
    return {
        "enabled": cfg["enabled"],
        "paid": await is_paid(tg_id, is_admin),
        "expires": int((row or {}).get("expires_at") or 0) if row else None,
        "days": cfg["days"],
        "zarinpal": uses_zarinpal(cfg),
        "stars": uses_stars(cfg),
        "amount": cfg["amount"],
        "starsPrice": cfg["stars"],
    }


__all__ = [
    "GATEWAYS",
    "PaymentError",
    "bind_bot",
    "callback_url",
    "config",
    "enabled",
    "grant",
    "is_paid",
    "public_state",
    "recent",
    "revoke",
    "stars_check",
    "stars_invoice_link",
    "stars_paid",
    "stats",
    "subscription",
    "uses_stars",
    "uses_zarinpal",
    "zarinpal_start",
    "zarinpal_verify",
]
