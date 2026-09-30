"""Outer middleware: user context, gating, and a light per-user rate limit."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from . import db, keyboards, payment, referral
from .config import settings
from .i18n import normalise, t

log = logging.getLogger("autovless.middleware")

ALLOWED_WHILE_LOCKED = {"join:check", "nav:lang"}
# The invite lock has to leave a way to *earn* the unlock, so the invite card,
# the recheck button and the language switch always pass.
ALLOWED_WHILE_UNPAID = {"ref:check", "nav:invite", "nav:lang", "join:check"}
UNPAID_COMMANDS = ("/start", "/invite", "/cancel")
# The paywall, likewise, must leave a way to pay: every ``pay:`` callback, the
# language switch and the commands that draw the pay screen.
ALLOWED_WHILE_NOT_PAID = {"nav:lang", "join:check"}
NOT_PAID_COMMANDS = ("/start", "/pay", "/cancel")
MEMBER_STATES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}


def _actor(event: Update) -> User | None:
    if event.message:
        return event.message.from_user
    if event.callback_query:
        return event.callback_query.from_user
    if event.edited_message:
        return event.edited_message.from_user
    return None


def _is_payment(event: Update) -> bool:
    """A settled payment is never blocked by any lock: the money already moved."""
    return bool(event.message and event.message.successful_payment)


async def _reply(event: Update, text: str, markup: Any = None) -> None:
    if event.callback_query:
        await event.callback_query.answer()
        if event.callback_query.message:
            await event.callback_query.message.answer(text, reply_markup=markup)
        return
    if event.message:
        await event.message.answer(text, reply_markup=markup)


class ContextMiddleware(BaseMiddleware):
    """Loads or creates the user row and injects language plus admin flag."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        actor = _actor(event)
        if actor is None or actor.is_bot:
            return await handler(event, data)

        user = await db.upsert_user(actor.id, actor.username, actor.first_name)
        lang = normalise(user["lang"])
        is_admin = settings.is_admin(actor.id)

        data["user"] = user
        data["lang"] = lang
        data["is_admin"] = is_admin

        if user["is_banned"] and not is_admin:
            await _reply(event, t(lang, "banned"))
            return None

        if await db.get_flag("maintenance") and not is_admin and not _is_payment(event):
            await _reply(event, t(lang, "maintenance"))
            return None

        return await handler(event, data)


class ChannelLockMiddleware(BaseMiddleware):
    """Forced membership. Admins and the unlock button itself always pass."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        actor = _actor(event)
        if actor is None or data.get("is_admin") or _is_payment(event):
            return await handler(event, data)

        callback = event.callback_query
        if callback is not None and (callback.data or "") in ALLOWED_WHILE_LOCKED:
            return await handler(event, data)

        if not await db.get_flag("force_join"):
            return await handler(event, data)

        channels = await db.channels()
        if not channels:
            return await handler(event, data)

        bot: Bot = data["bot"]
        missing = await missing_channels(bot, actor.id, channels)
        if not missing:
            return await handler(event, data)

        lang = data.get("lang", settings.default_lang)
        await _reply(event, t(lang, "join_required"), keyboards.join_menu(lang, missing))
        return None


class ReferralLockMiddleware(BaseMiddleware):
    """The invite quota. Everything is closed until the user has brought N people.

    ``/start`` is deliberately never blocked: the link the user is being asked to
    share *is* a ``/start`` link, so blocking it would make the quota impossible
    to fill and would silently swallow every invite that arrived.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        actor = _actor(event)
        if actor is None or data.get("is_admin") or _is_payment(event):
            return await handler(event, data)

        if not await referral.enabled():
            return await handler(event, data)

        callback = event.callback_query
        if callback is not None and (callback.data or "") in ALLOWED_WHILE_UNPAID:
            return await handler(event, data)

        message = event.message
        if message is not None:
            text = (message.text or "").strip().lower()
            if text.startswith(UNPAID_COMMANDS):
                return await handler(event, data)

        if await referral.unlocked(actor.id):
            return await handler(event, data)

        lang = data.get("lang", settings.default_lang)
        bot: Bot = data["bot"]
        body, markup = await referral.gate_text(bot, actor.id, lang)
        await _reply(event, body, markup)
        return None


class PaywallMiddleware(BaseMiddleware):
    """Paid entry. Nothing opens until the user has an active payment.

    Runs after the channel and invite locks, so a user meets them in a sensible
    order: join, invite (if the admin wants both), then pay. ``pay:`` callbacks,
    ``/start`` and ``/pay`` always pass because they *are* the way to pay, and a
    settled payment update is never blocked.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        actor = _actor(event)
        if actor is None or data.get("is_admin") or _is_payment(event):
            return await handler(event, data)

        if not await payment.enabled():
            return await handler(event, data)

        callback = event.callback_query
        if callback is not None:
            name = callback.data or ""
            if name.startswith("pay:") or name in ALLOWED_WHILE_NOT_PAID:
                return await handler(event, data)

        message = event.message
        if message is not None:
            text = (message.text or "").strip().lower()
            if text.startswith(NOT_PAID_COMMANDS):
                return await handler(event, data)

        if await payment.is_paid(actor.id):
            return await handler(event, data)

        # Imported here: the handlers package imports this module, so a top-level
        # import would be circular.
        from .handlers.payment import gate

        lang = data.get("lang", settings.default_lang)
        body, markup = await gate(lang)
        await _reply(event, body, markup)
        return None


async def missing_channels(bot: Bot, tg_id: int, channels: list[dict]) -> list[dict]:
    """Channels the user has not joined. Unreachable channels are skipped."""
    missing: list[dict] = []
    for channel in channels:
        chat_id: Any = channel["chat_id"]
        if str(chat_id).lstrip("-").isdigit():
            chat_id = int(chat_id)
        try:
            member = await bot.get_chat_member(chat_id, tg_id)
        except Exception as error:  # noqa: BLE001
            log.warning("channel %s is unreachable: %s", chat_id, error)
            continue
        status = member.status
        joined = status in MEMBER_STATES or (
            status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False)
        )
        if not joined:
            missing.append(channel)
    return missing


class ThrottleMiddleware(BaseMiddleware):
    """One action per user per interval, so a 1 vCPU box stays responsive."""

    def __init__(self, interval: float = 0.6) -> None:
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        actor = _actor(event)
        if actor is None or _is_payment(event):
            return await handler(event, data)

        now = time.monotonic()
        previous = self._last.get(actor.id, 0.0)
        if now - previous < self.interval:
            if event.callback_query:
                await event.callback_query.answer()
            return None
        self._last[actor.id] = now

        if len(self._last) > 5000:
            cutoff = now - 300
            self._last = {k: v for k, v in self._last.items() if v > cutoff}

        return await handler(event, data)


def register(dispatcher: Any) -> None:
    dispatcher.update.outer_middleware(ContextMiddleware())
    dispatcher.update.outer_middleware(ThrottleMiddleware())
    dispatcher.update.outer_middleware(ChannelLockMiddleware())
    dispatcher.update.outer_middleware(ReferralLockMiddleware())
    dispatcher.update.outer_middleware(PaywallMiddleware())
