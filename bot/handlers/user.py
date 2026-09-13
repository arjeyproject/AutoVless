"""Start, main menu, static screens, language and operator selection."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards, operators, referral, screens
from ..config import settings
from ..i18n import other_lang, t
from ..middlewares import missing_channels
from ..utils import edit, esc

log = logging.getLogger("autovless.handlers.user")
router = Router(name="user")


@router.message(CommandStart())
async def on_start(
    message: Message,
    state: FSMContext,
    lang: str,
    is_admin: bool,
    command: CommandObject | None = None,
) -> None:
    await state.clear()
    name = message.from_user.first_name or message.from_user.username or ""
    await db.log_event("start", message.from_user.id, f"@{message.from_user.username or '-'}")

    # An invite link is a /start link, so this is the only place an invite can be
    # counted. It is credited before the gate is drawn, so somebody arriving on a
    # friend's link never sees the lock at all.
    inviter = referral.parse_payload(command.args if command else "")
    if inviter:
        try:
            await referral.credit(message.bot, inviter, message.from_user.id, esc(name))
        except Exception:  # noqa: BLE001
            log.debug("could not credit an invite", exc_info=True)

    if not await referral.unlocked(message.from_user.id, is_admin):
        body, markup = await referral.gate_text(message.bot, message.from_user.id, lang)
        await message.answer(body, reply_markup=markup, disable_web_page_preview=True)
        return

    # One screen, not two. The old flow sent the menu and then a second note
    # underneath it, which pushed the buttons up the chat and looked broken.
    text, markup = await screens.main_menu(name, lang, is_admin)
    await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.message(Command("menu"))
async def on_menu_command(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    await state.clear()
    name = message.from_user.first_name or ""
    text, markup = await screens.main_menu(name, lang, is_admin)
    await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(t(lang, "cancelled"))


@router.callback_query(F.data == "nav:menu")
async def on_menu(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    await state.clear()
    name = call.from_user.first_name or ""
    text, markup = await screens.main_menu(name, lang, is_admin)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data == "nav:lang")
async def on_language(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    new_lang = other_lang(lang)
    await db.set_lang(call.from_user.id, new_lang)
    if not await referral.unlocked(call.from_user.id, is_admin):
        body, markup = await referral.gate_text(call.bot, call.from_user.id, new_lang)
        await edit(call, body, markup)
        await call.answer()
        return
    name = call.from_user.first_name or ""
    text, markup = await screens.main_menu(name, new_lang, is_admin)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data == "nav:status")
async def on_status(call: CallbackQuery, lang: str) -> None:
    text, markup = await screens.network_status(lang)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data == "nav:guide")
async def on_guide(call: CallbackQuery, lang: str) -> None:
    await edit(call, t(lang, "guide"), keyboards.apps_platforms(lang))
    await call.answer()


@router.callback_query(F.data == "nav:donate")
async def on_donate(call: CallbackQuery, lang: str) -> None:
    await edit(call, t(lang, "support_us", brand=esc(settings.brand)), keyboards.simple_back(lang))
    await call.answer()


@router.callback_query(F.data == "nav:operator")
async def on_operator(call: CallbackQuery, lang: str) -> None:
    user = await db.get_user(call.from_user.id)
    text, markup = screens.operator_screen(lang, user["operator"] if user else None)
    await edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data.startswith("op:"))
async def on_operator_pick(call: CallbackQuery, lang: str) -> None:
    code = (call.data or "").split(":", 1)[1]
    if code not in operators.OPERATORS:
        await call.answer()
        return
    await db.set_operator(call.from_user.id, code)
    text = t(
        lang,
        "operator_saved",
        operator=esc(operators.label(code, lang)),
        tip=esc(operators.tip(code, lang)),
    )
    await edit(call, text, keyboards.simple_back(lang))
    await call.answer()


@router.callback_query(F.data == "join:check")
async def on_join_check(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    channels = await db.channels()
    missing = await missing_channels(call.bot, call.from_user.id, channels) if channels else []
    if missing:
        await call.answer(t(lang, "join_fail"), show_alert=True)
        return
    name = call.from_user.first_name or ""
    text, markup = await screens.main_menu(name, lang, is_admin)
    await edit(call, text, markup)
    await call.answer(t(lang, "join_ok"))
