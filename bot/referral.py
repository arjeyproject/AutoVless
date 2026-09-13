"""The forced-invite lock.

The rule is simple and the admin owns both halves of it: turn it on, and say how
many people each user has to bring. Until they do, the bot answers with one
screen - their own link, their own progress, and a nudge - and nothing else.

Admins are never locked out, the language button always works, and ``/start``
always runs, because the link a user is being asked to share is a ``/start`` link
and blocking it would make the whole thing unwinnable.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import db, store
from .config import settings
from .i18n import num, t

log = logging.getLogger("autovless.referral")

PAYLOAD_PREFIX = "ref"
FULL = "\u25c6"
EMPTY = "\u25c7"
MAX_REQUIRED = 50

_username: str = ""


async def bot_username(bot: Bot) -> str:
    """Cached, because every gate screen needs it and it never changes."""
    global _username
    if not _username:
        try:
            me = await bot.me()
            _username = str(me.username or "")
        except Exception:  # noqa: BLE001
            log.debug("could not read the bot username", exc_info=True)
    return _username


def cached_username() -> str:
    """The username the invite link is built from, without needing a Bot handle.

    Filled once at startup and on the first gate screen. The API runs in the same
    process, so by the time anybody can open the mini app it is set.
    """
    return _username


async def enabled() -> bool:
    return await store.flag("referral_lock")


async def required() -> int:
    return max(0, min(MAX_REQUIRED, await store.get_int("referral_required", 3)))


async def invited(tg_id: int) -> int:
    return await store.referral_count(tg_id)


async def unlocked(tg_id: int, is_admin: bool = False) -> bool:
    if is_admin:
        return True
    if not await enabled():
        return True
    goal = await required()
    if goal <= 0:
        return True
    return await invited(tg_id) >= goal


def link(username: str, tg_id: int) -> str:
    if not username:
        return ""
    return f"https://t.me/{username}?start={PAYLOAD_PREFIX}{int(tg_id)}"


def parse_payload(payload: str) -> Optional[int]:
    """``ref12345`` -> 12345. Anything else is not an invite."""
    text = str(payload or "").strip()
    if not text.lower().startswith(PAYLOAD_PREFIX):
        return None
    digits = text[len(PAYLOAD_PREFIX) :].strip()
    if not digits.isdigit():
        return None
    return int(digits)


def bar(done: int, goal: int, width: int = 10) -> str:
    if goal <= 0:
        return FULL * width
    filled = max(0, min(width, round(width * done / goal)))
    return FULL * filled + EMPTY * (width - filled)


def gate_keyboard(lang: str, invite: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if invite:
        share = (
            "https://t.me/share/url?url="
            + invite.replace(":", "%3A").replace("/", "%2F")
            + "&text="
            + ("%F0%9F%9A%80")
        )
        rows.append([InlineKeyboardButton(text=t(lang, "btn.ref_share"), url=share)])
    rows.append([InlineKeyboardButton(text=t(lang, "btn.ref_check"), callback_data="ref:check")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn.lang"), callback_data="nav:lang")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_keyboard(lang: str, invite: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if invite:
        share = "https://t.me/share/url?url=" + invite.replace(":", "%3A").replace("/", "%2F")
        rows.append([InlineKeyboardButton(text=t(lang, "btn.ref_share"), url=share)])
    rows.append([InlineKeyboardButton(text=t(lang, "btn.ref_check"), callback_data="ref:check")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn.back"), callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def gate_text(bot: Bot, tg_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    goal = await required()
    done = await invited(tg_id)
    invite = link(await bot_username(bot), tg_id)
    text = t(
        lang,
        "ref.gate",
        required=num(goal, lang),
        invited=num(done, lang),
        bar=bar(done, goal),
        link=invite or "-",
    )
    return text, gate_keyboard(lang, invite)


async def card(bot: Bot, tg_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    goal = await required()
    done = await invited(tg_id)
    invite = link(await bot_username(bot), tg_id)

    if not await enabled() or goal <= 0:
        state = t(lang, "ref.state_off")
    elif done >= goal:
        state = t(lang, "ref.state_open")
    else:
        state = t(lang, "ref.state_locked", left=num(goal - done, lang))

    text = t(
        lang,
        "ref.card",
        link=invite or "-",
        invited=num(done, lang),
        required=num(goal, lang),
        bar=bar(done, goal),
        state=state,
    )
    return text, card_keyboard(lang, invite)


async def credit(bot: Bot, inviter: int, invitee: int, name: str = "") -> bool:
    """Count an arrival and tell the inviter about it."""
    if not await store.credit_referral(inviter, invitee):
        return False

    total = await invited(inviter)
    try:
        row = await db.get_user(inviter)
        lang = str((row["lang"] if row is not None else "") or settings.default_lang)
        await bot.send_message(
            inviter,
            t(lang, "ref.credited", name=name or "\u2728", invited=num(total, lang)),
        )
    except Exception:  # noqa: BLE001
        log.debug("could not notify inviter %s", inviter, exc_info=True)
    return True
