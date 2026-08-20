"""Outer middleware: user context, gating, and a light per-user rate limit."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from . import db, keyboards
from .config import settings
from .i18n import normalise, t

log = logging.getLogger("autovless.middleware")

ALLOWED_WHILE_LOCKED = {"join:check", "nav:lang"}
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

        if await db.get_flag("maintenance") and not is_admin:
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
        if actor is None or data.get("is_admin"):
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
        if actor is None:
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
