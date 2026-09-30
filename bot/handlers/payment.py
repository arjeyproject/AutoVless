"""Paid entry: the user's pay screen, Telegram Stars, and the admin controls.

Registered first, ahead of ``adminx``, because it owns every ``pay:`` and
``adm:pay`` callback plus the two update types Stars needs
(``pre_checkout_query`` and ``successful_payment``). Neither of those can be
allowed to fall through to a broader router: a pre-checkout query that nobody
answers within ten seconds is a payment Telegram cancels on the user.
"""

from __future__ import annotations

import datetime as dt
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from .. import db, keyboards, payment, screens
from ..config import settings
from ..i18n import num, t
from ..utils import edit, esc

log = logging.getLogger("autovless.handlers.payment")
router = Router(name="payment")

MERCHANT_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class PayFlow(StatesGroup):
    amount = State()
    stars = State()
    days = State()
    merchant = State()
    grant = State()
    revoke = State()


def _b(label: str, data: str = "", url: str = "") -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=label, url=url)
    return InlineKeyboardButton(text=label, callback_data=data)


def _money(value: int) -> str:
    return f"{int(value):,}"


def period(days: int, lang: str) -> str:
    if int(days) <= 0:
        return t(lang, "pay.period_forever")
    return t(lang, "pay.period_days", days=num(days, lang))


def until(expires: int, lang: str) -> str:
    if not expires:
        return t(lang, "pay.until_forever")
    date = dt.datetime.fromtimestamp(int(expires)).strftime("%Y-%m-%d")
    return t(lang, "pay.until", date=num(date, lang))


def price_line(cfg: dict, lang: str) -> str:
    parts: list[str] = []
    if payment.uses_zarinpal(cfg):
        parts.append(t(lang, "pay.price_toman", amount=num(_money(cfg["amount"]), lang)))
    if payment.uses_stars(cfg):
        parts.append(t(lang, "pay.price_stars", stars=num(cfg["stars"], lang)))
    return t(lang, "pay.or").join(parts) or "-"


# --------------------------------------------------------------------- #
# the gate a user sees
# --------------------------------------------------------------------- #


async def gate(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    cfg = await payment.config()
    rows: list[list[InlineKeyboardButton]] = []
    if payment.uses_zarinpal(cfg):
        rows.append([_b(t(lang, "btn.pay_zp"), "pay:zp")])
    if payment.uses_stars(cfg):
        rows.append([_b(t(lang, "btn.pay_stars"), "pay:stars")])
    if not rows:
        text = t(lang, "pay.no_gateway")
    else:
        text = t(
            lang,
            "pay.gate",
            brand=esc(settings.brand),
            price=price_line(cfg, lang),
            period=period(cfg["days"], lang),
        )
        rows.append([_b(t(lang, "btn.pay_check"), "pay:check")])
    bottom = [_b(t(lang, "btn.lang"), "nav:lang")]
    if settings.support_url:
        bottom.append(_b(t(lang, "btn.pay_support"), url=settings.support_url))
    rows.append(bottom)
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def show_gate(event: CallbackQuery | Message, lang: str) -> None:
    text, markup = await gate(lang)
    await edit(event, text, markup)


async def _open_menu(event: CallbackQuery | Message, lang: str, is_admin: bool) -> None:
    user = event.from_user
    name = (user.first_name or user.username or "") if user else ""
    text, markup = await screens.main_menu(name, lang, is_admin)
    await edit(event, text, markup)


@router.message(Command("pay"))
async def on_pay_command(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    await state.clear()
    row = await payment.subscription(message.from_user.id)
    if await payment.enabled() and await payment.is_paid(message.from_user.id, is_admin) and row:
        await message.answer(
            t(lang, "pay.active", until=until(int(row.get("expires_at") or 0), lang))
        )
        return
    await show_gate(message, lang)


@router.callback_query(F.data == "pay:check")
async def on_check(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if await payment.is_paid(call.from_user.id, is_admin):
        await call.answer("\u2705")
        await _open_menu(call, lang, is_admin)
        return
    await call.answer(t(lang, "pay.pending"), show_alert=True)


@router.callback_query(F.data == "pay:zp")
async def on_zarinpal(call: CallbackQuery, lang: str) -> None:
    cfg = await payment.config()
    await call.answer()
    try:
        url = await payment.zarinpal_start(call.from_user.id)
    except payment.PaymentError as error:
        await call.message.answer(t(lang, "pay.failed", reason=esc(error)))
        return
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pay_open"), url=url)],
            [_b(t(lang, "btn.pay_check"), "pay:check")],
        ]
    )
    await call.message.answer(
        t(lang, "pay.zp_link", price=t(lang, "pay.price_toman", amount=num(_money(cfg["amount"]), lang))),
        reply_markup=markup,
    )


@router.callback_query(F.data == "pay:stars")
async def on_stars(call: CallbackQuery, lang: str) -> None:
    cfg = await payment.config()
    if not payment.uses_stars(cfg):
        await call.answer(t(lang, "pay.no_gateway"), show_alert=True)
        return
    await call.answer()
    span = period(cfg["days"], lang)
    try:
        await call.bot.send_invoice(
            chat_id=call.from_user.id,
            title=t(lang, "pay.stars_title", brand=settings.brand)[:32],
            description=t(lang, "pay.stars_desc", brand=settings.brand, period=span)[:255],
            payload=payment.stars_payload(call.from_user.id),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=t(lang, "pay.stars_label")[:32], amount=int(cfg["stars"]))],
        )
    except Exception as error:  # noqa: BLE001
        log.warning("could not send a stars invoice: %s", error)
        await call.message.answer(t(lang, "pay.failed", reason=esc(str(error)[:160])))


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Answered for every query, always: silence here cancels the payment."""
    try:
        ok = await payment.stars_check(
            query.from_user.id, query.invoice_payload, query.total_amount, query.currency
        )
    except Exception:  # noqa: BLE001
        log.exception("pre-checkout validation failed")
        ok = False
    if ok:
        await query.answer(ok=True)
        return
    row = await db.get_user(query.from_user.id)
    lang = str((row["lang"] if row is not None else "") or settings.default_lang)
    await query.answer(ok=False, error_message=t(lang, "pay.precheckout_bad"))


@router.message(F.successful_payment)
async def on_paid(message: Message, lang: str, is_admin: bool) -> None:
    info = message.successful_payment
    if info is None or info.currency != "XTR":
        return
    if payment.payload_user(info.invoice_payload) != message.from_user.id:
        log.warning("stars payload for another user from %s", message.from_user.id)
    expires = await payment.stars_paid(
        message.from_user.id, int(info.total_amount), str(info.telegram_payment_charge_id)
    )
    await message.answer(
        t(
            lang,
            "pay.done",
            ref=esc(info.telegram_payment_charge_id),
            until=until(expires, lang),
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_b(t(lang, "btn.pay_menu"), "nav:menu")]]
        ),
    )


async def notify_paid(tg_id: int, ref: str, expires: int) -> None:
    """Called by the Zarinpal callback, which runs outside any handler."""
    bot = payment.bot()
    if bot is None:
        return
    try:
        row = await db.get_user(tg_id)
        lang = str((row["lang"] if row is not None else "") or settings.default_lang)
        await bot.send_message(
            tg_id,
            t(lang, "pay.done", ref=esc(ref or "-"), until=until(expires, lang)),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_b(t(lang, "btn.pay_menu"), "nav:menu")]]
            ),
        )
    except Exception:  # noqa: BLE001
        log.debug("could not tell %s about their payment", tg_id, exc_info=True)


# --------------------------------------------------------------------- #
# admin
# --------------------------------------------------------------------- #


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.pay_toggle"), "adm:pay:toggle"), _b(t(lang, "btn.pay_gw"), "adm:pay:gw")],
            [_b(t(lang, "btn.pay_amount"), "adm:pay:amount"), _b(t(lang, "btn.pay_stars_price"), "adm:pay:stars")],
            [_b(t(lang, "btn.pay_days"), "adm:pay:days"), _b(t(lang, "btn.pay_merchant"), "adm:pay:merchant")],
            [_b(t(lang, "btn.pay_sandbox"), "adm:pay:sandbox"), _b(t(lang, "btn.pay_list"), "adm:pay:list")],
            [_b(t(lang, "btn.pay_grant"), "adm:pay:grant"), _b(t(lang, "btn.pay_revoke"), "adm:pay:revoke")],
            [_b(t(lang, "btn.back"), "adm:menu")],
        ]
    )


def _mask(merchant: str) -> str:
    if not merchant:
        return "-"
    return merchant[:8] + "\u2026" + merchant[-4:]


async def show_admin(event: CallbackQuery | Message, lang: str) -> None:
    cfg = await payment.config()
    stats = await payment.stats()
    callback = payment.callback_url() or "-"
    warning = ""
    if cfg["gateway"] in {"zarinpal", "both"} and (not cfg["merchant"] or not callback.startswith("https://")):
        warning = t(lang, "admin.pay_warn_zp")
    elif not payment.uses_zarinpal(cfg) and not payment.uses_stars(cfg):
        warning = t(lang, "admin.pay_warn_none")
    text = t(
        lang,
        "admin.pay",
        state=t(lang, "admin.on" if cfg["enabled"] else "admin.off"),
        gateway=t(lang, f"admin.pay_gw_{cfg['gateway']}"),
        amount=num(_money(cfg["amount"]), lang),
        stars=num(cfg["stars"], lang),
        period=period(cfg["days"], lang),
        merchant=esc(_mask(cfg["merchant"])),
        sandbox=t(lang, "admin.on" if cfg["sandbox"] else "admin.off"),
        callback=esc(callback),
        active=num(stats["active"], lang),
        subscribers=num(stats["subscribers"], lang),
        toman=num(_money(stats["toman"]), lang),
        earned=num(stats["stars"], lang),
        paid=num(stats["paid"], lang),
        pending=num(stats["pending"], lang),
        warning=warning,
    )
    await edit(event, text, admin_menu(lang))


def _denied(call: CallbackQuery, lang: str):
    return call.answer(t(lang, "admin.denied"), show_alert=True)


@router.callback_query(F.data == "adm:pay")
async def on_admin(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        await _denied(call, lang)
        return
    await state.clear()
    await show_admin(call, lang)
    await call.answer()


@router.callback_query(F.data.in_({"adm:pay:toggle", "adm:pay:sandbox", "adm:pay:gw"}))
async def on_admin_switch(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not is_admin:
        await _denied(call, lang)
        return
    action = (call.data or "").rsplit(":", 1)[-1]
    if action == "toggle":
        value = await payment.toggle("pay_enabled")
        detail = f"pay_enabled={value}"
    elif action == "sandbox":
        value = await payment.toggle("pay_sandbox")
        detail = f"pay_sandbox={value}"
    else:
        current = (await payment.config())["gateway"]
        order = payment.GATEWAYS
        value = order[(order.index(current) + 1) % len(order)] if current in order else order[0]
        await payment.put("pay_gateway", value)
        detail = f"pay_gateway={value}"
    await db.log_event("option", call.from_user.id, detail)
    await show_admin(call, lang)
    await call.answer(t(lang, "admin.pay_saved"))


PROMPTS: dict[str, tuple[State, str]] = {
    "amount": (PayFlow.amount, "admin.pay_prompt_amount"),
    "stars": (PayFlow.stars, "admin.pay_prompt_stars"),
    "days": (PayFlow.days, "admin.pay_prompt_days"),
    "merchant": (PayFlow.merchant, "admin.pay_prompt_merchant"),
    "grant": (PayFlow.grant, "admin.pay_prompt_grant"),
    "revoke": (PayFlow.revoke, "admin.pay_prompt_revoke"),
}


@router.callback_query(F.data.in_({f"adm:pay:{key}" for key in PROMPTS}))
async def on_admin_prompt(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        await _denied(call, lang)
        return
    key = (call.data or "").rsplit(":", 1)[-1]
    target, prompt = PROMPTS[key]
    await state.set_state(target)
    await edit(call, t(lang, prompt), keyboards.simple_back(lang, "adm:pay"))
    await call.answer()


async def _number(message: Message, lang: str, low: int, high: int) -> int | None:
    raw = (message.text or "").strip().replace(",", "").replace("\u066c", "")
    raw = raw.translate(str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9", "0123456789"))
    if not raw.isdigit() or not (low <= int(raw) <= high):
        await message.answer(t(lang, "admin.pay_bad_number"))
        return None
    return int(raw)


async def _saved(message: Message, state: FSMContext, lang: str, detail: str) -> None:
    await state.clear()
    await db.log_event("option", message.from_user.id, detail)
    await message.answer(t(lang, "admin.pay_saved"))
    await show_admin(message, lang)


@router.message(PayFlow.amount, F.text, ~F.text.startswith("/"))
async def on_amount(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    value = await _number(message, lang, 1000, 1_000_000_000)
    if value is None:
        return
    await payment.put("pay_amount", value)
    await _saved(message, state, lang, f"pay_amount={value}")


@router.message(PayFlow.stars, F.text, ~F.text.startswith("/"))
async def on_stars_price(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    value = await _number(message, lang, 1, 100_000)
    if value is None:
        return
    await payment.put("pay_stars", value)
    await _saved(message, state, lang, f"pay_stars={value}")


@router.message(PayFlow.days, F.text, ~F.text.startswith("/"))
async def on_days(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    value = await _number(message, lang, 0, 3650)
    if value is None:
        return
    await payment.put("pay_days", value)
    await _saved(message, state, lang, f"pay_days={value}")


@router.message(PayFlow.merchant, F.text, ~F.text.startswith("/"))
async def on_merchant(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    elif not MERCHANT_RE.match(raw):
        await message.answer(t(lang, "admin.pay_bad_merchant"))
        return
    await payment.put("pay_merchant", raw)
    try:
        # The merchant id is a credential; do not leave it sitting in the chat.
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await _saved(message, state, lang, "pay_merchant=***")


@router.message(PayFlow.grant, F.text, ~F.text.startswith("/"))
async def on_grant(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    parts = (message.text or "").split()
    if not parts or not parts[0].lstrip("-").isdigit() or (len(parts) > 1 and not parts[1].isdigit()):
        await message.answer(t(lang, "admin.pay_bad_number"))
        return
    user = int(parts[0])
    days = int(parts[1]) if len(parts) > 1 else None
    expires = await payment.grant(user, days)
    await state.clear()
    await db.log_event("payment_grant", message.from_user.id, f"{user} days={days}")
    await message.answer(
        t(lang, "admin.pay_granted", user=user, until=until(expires, lang)),
        reply_markup=keyboards.simple_back(lang, "adm:pay"),
    )
    try:
        row = await db.get_user(user)
        user_lang = str((row["lang"] if row is not None else "") or settings.default_lang)
        await message.bot.send_message(
            user, t(user_lang, "pay.user_granted", until=until(expires, user_lang))
        )
    except Exception:  # noqa: BLE001
        log.debug("could not notify granted user %s", user, exc_info=True)


@router.message(PayFlow.revoke, F.text, ~F.text.startswith("/"))
async def on_revoke(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not is_admin:
        return
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(t(lang, "admin.pay_bad_number"))
        return
    await state.clear()
    existed = await payment.revoke(int(raw))
    await db.log_event("payment_revoke", message.from_user.id, raw)
    await message.answer(
        t(lang, "admin.pay_revoked" if existed else "admin.pay_revoke_none", user=raw),
        reply_markup=keyboards.simple_back(lang, "adm:pay"),
    )


@router.callback_query(F.data == "adm:pay:list")
async def on_admin_list(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not is_admin:
        await _denied(call, lang)
        return
    rows = await payment.recent(12)
    lines = []
    for row in rows:
        amount = (
            t(lang, "pay.price_toman", amount=num(_money(int(row["amount"]) // 10), lang))
            if row["currency"] == "IRR"
            else t(lang, "pay.price_stars", stars=num(row["amount"], lang))
        )
        stamp = dt.datetime.fromtimestamp(int(row.get("paid_at") or 0)).strftime("%m-%d %H:%M")
        who = esc(row.get("first_name") or row.get("username") or row["tg_id"])
        lines.append(f"\u2022 {who} <code>{row['tg_id']}</code> \u00b7 {amount} \u00b7 {num(stamp, lang)}")
    listing = "\n".join(lines) or t(lang, "admin.pay_list_empty")
    await edit(call, t(lang, "admin.pay_list", list=listing), keyboards.simple_back(lang, "adm:pay"))
    await call.answer()
