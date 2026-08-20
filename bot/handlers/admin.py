"""Admin panel: stats, users, broadcast, channel lock, engine, options, backup."""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import db, keyboards
from ..config import settings
from ..i18n import num, t
from ..scanner import scanner
from ..utils import ago, edit, esc, ping_label

log = logging.getLogger("autovless.admin")
router = Router(name="admin")

OPTION_KEYS = ("maintenance", "builds_enabled", "force_join")


class AdminFlow(StatesGroup):
    user_search = State()
    broadcast = State()
    channel = State()


def _guard(is_admin: bool) -> bool:
    return bool(is_admin)


@router.callback_query(F.data.startswith("adm:"))
async def dispatch(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return

    action = (call.data or "adm:menu").split(":", 1)[1]

    if action == "menu":
        await state.clear()
        await show_menu(call, lang)
    elif action == "stats":
        await show_stats(call, lang)
    elif action == "users":
        await state.set_state(AdminFlow.user_search)
        await edit(call, t(lang, "admin.users_prompt"), keyboards.simple_back(lang, "adm:menu"))
    elif action == "broadcast":
        await state.set_state(AdminFlow.broadcast)
        recipients = len(await db.all_user_ids())
        await edit(
            call,
            t(lang, "admin.broadcast_prompt", count=num(recipients, lang)),
            keyboards.simple_back(lang, "adm:menu"),
        )
    elif action == "channels":
        await state.clear()
        await show_channels(call, lang)
    elif action == "chadd":
        await state.set_state(AdminFlow.channel)
        await edit(call, t(lang, "admin.channel_prompt"), keyboards.simple_back(lang, "adm:channels"))
    elif action.startswith("chdel:"):
        await db.remove_channel(action.split(":", 1)[1])
        await call.answer(t(lang, "admin.channel_removed"))
        await show_channels(call, lang)
        return
    elif action == "engine":
        await show_engine(call, lang)
    elif action == "scan":
        await call.answer(t(lang, "scan_started"))
        await scanner.scan_once(batch=max(320, settings.scan_batch // 2))
        await show_engine(call, lang)
        return
    elif action == "options":
        await show_options(call, lang)
    elif action.startswith("opt:"):
        key = action.split(":", 1)[1]
        if key in OPTION_KEYS:
            await db.toggle_flag(key)
            await db.log_event("option", call.from_user.id, key)
        await show_options(call, lang)
    elif action == "panels":
        await show_panels(call, lang)
    elif action == "logs":
        await show_logs(call, lang)
    elif action == "backup":
        await send_backup(call, lang)
    elif action.startswith(("ban:", "unban:")):
        verb, raw_id = action.split(":", 1)
        target = int(raw_id)
        await db.set_banned(target, verb == "ban")
        await db.log_event(verb, call.from_user.id, str(target))
        await call.answer(t(lang, "admin.ban_done" if verb == "ban" else "admin.unban_done"))
        await show_user(call, lang, target)
        return

    await call.answer()


# --------------------------------------------------------------------- views


async def show_menu(call: CallbackQuery, lang: str) -> None:
    stats = await db.global_stats()
    pool = await db.pool_stats()
    text = t(
        lang,
        "admin.menu",
        users=num(stats["users"], lang),
        users_today=num(stats["users_today"], lang),
        panels=num(stats["panels"], lang),
        panels_today=num(stats["panels_today"], lang),
        pool=num(pool["total"], lang),
        channels=num(stats["channels"], lang),
        maintenance=t(lang, "admin.on" if await db.get_flag("maintenance") else "admin.off"),
        builds=t(lang, "admin.on" if await db.get_flag("builds_enabled") else "admin.off"),
    )
    await edit(call, text, keyboards.admin_menu(lang))


async def show_stats(call: CallbackQuery, lang: str) -> None:
    stats = await db.global_stats()
    pool = await db.pool_stats()
    text = t(
        lang,
        "admin.stats",
        users=num(stats["users"], lang),
        users_today=num(stats["users_today"], lang),
        active_week=num(stats["active_week"], lang),
        banned=num(stats["banned"], lang),
        panels=num(stats["panels"], lang),
        rebuilds=num(stats["rebuilds"], lang),
        avg_build=num(round(stats["avg_build_ms"] / 1000, 1), lang),
        verified=num(pool["verified"], lang),
        pool=num(pool["total"], lang),
    )
    await edit(call, text, keyboards.simple_back(lang, "adm:menu"))


async def show_channels(call: CallbackQuery, lang: str) -> None:
    channels = await db.channels()
    listing = "\n".join(
        f"\u2022 <b>{esc(channel.get('title') or channel['chat_id'])}</b> "
        f"\u00b7 <code>{esc(channel['chat_id'])}</code>"
        for channel in channels
    ) or t(lang, "admin.channels_empty")
    state = t(lang, "admin.on" if await db.get_flag("force_join") else "admin.off")
    await edit(
        call,
        t(lang, "admin.channels", state=state, list=listing),
        keyboards.admin_channels(lang, channels),
    )


async def show_engine(call: CallbackQuery, lang: str) -> None:
    stats = await scanner.stats()
    text = t(
        lang,
        "admin.engine",
        total=num(stats["total"], lang),
        verified=num(stats["verified"], lang),
        best=ping_label(stats["best"], lang),
        ports=" \u00b7 ".join(num(port, lang) for port in stats["ports"]),
        updated=ago(stats["updated_at"], lang),
        state=t(lang, "admin.on" if stats["scanning"] else "admin.off"),
        interval=num(settings.scan_interval, lang),
        batch=num(settings.scan_batch, lang),
        concurrency=num(settings.scan_concurrency, lang),
    )
    await edit(call, text, keyboards.admin_engine(lang))


async def show_options(call: CallbackQuery, lang: str) -> None:
    values = {key: await db.get_flag(key) for key in OPTION_KEYS}
    await edit(call, t(lang, "admin.options"), keyboards.admin_options(lang, values))


async def show_panels(call: CallbackQuery, lang: str) -> None:
    rows = await db.fetch_all(
        "SELECT p.host, p.rebuilds, p.updated_at, u.username, u.tg_id "
        "FROM panels p LEFT JOIN users u ON u.tg_id = p.tg_id "
        "ORDER BY p.updated_at DESC LIMIT 15"
    )
    listing = "\n".join(
        f"\u2022 <code>{esc(row['host'])}</code>\n  "
        f"@{esc(row['username'] or row['tg_id'])} \u00b7 "
        f"\U0001f504 {num(row['rebuilds'], lang)} \u00b7 {ago(row['updated_at'], lang)}"
        for row in rows
    ) or "-"
    await edit(call, t(lang, "admin.panels", list=listing), keyboards.simple_back(lang, "adm:menu"))


async def show_logs(call: CallbackQuery, lang: str) -> None:
    events = await db.recent_events(15)
    listing = "\n".join(
        f"\u2022 <b>{esc(event['kind'])}</b> \u00b7 {ago(event['at'], lang)}\n  "
        f"<code>{esc(event['detail'] or '-')}</code>"
        for event in events
    ) or "-"
    await edit(call, t(lang, "admin.logs", list=listing), keyboards.simple_back(lang, "adm:menu"))


async def show_user(call: CallbackQuery, lang: str, tg_id: int) -> None:
    user = await db.get_user(tg_id)
    if user is None:
        await edit(call, t(lang, "admin.user_none"), keyboards.simple_back(lang, "adm:menu"))
        return
    panel = await db.get_panel(tg_id)
    text = t(
        lang,
        "admin.user_card",
        name=esc(user["first_name"] or "-"),
        tg_id=num(tg_id, lang),
        username=f"@{esc(user['username'])}" if user["username"] else "-",
        lang=esc(user["lang"]),
        operator=esc(user["operator"] or "-"),
        panel=f"<code>{esc(panel['host'])}</code>" if panel else "-",
        builds=num(user["builds"], lang),
        banned=t(lang, "admin.on" if user["is_banned"] else "admin.off"),
        seen=ago(user["seen_at"], lang),
    )
    await edit(call, text, keyboards.admin_user(lang, tg_id, bool(user["is_banned"])))


async def send_backup(call: CallbackQuery, lang: str) -> None:
    payload = settings.db_path.read_bytes()
    stamp = time.strftime("%Y-%m-%d-%H%M")
    await call.message.answer_document(
        BufferedInputFile(payload, filename=f"autovless-{stamp}.db"),
        caption=t(lang, "admin.backup_caption", when=esc(stamp)),
        reply_markup=keyboards.simple_back(lang, "adm:menu"),
    )


# ------------------------------------------------------------------ intake


@router.message(AdminFlow.user_search, F.text)
async def on_user_search(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        return
    await state.clear()
    matches = await db.find_users(message.text or "")
    if not matches:
        await message.answer(t(lang, "admin.user_none"), reply_markup=keyboards.simple_back(lang, "adm:menu"))
        return

    if len(matches) == 1:
        user = matches[0]
        panel = await db.get_panel(user["tg_id"])
        text = t(
            lang,
            "admin.user_card",
            name=esc(user["first_name"] or "-"),
            tg_id=num(user["tg_id"], lang),
            username=f"@{esc(user['username'])}" if user["username"] else "-",
            lang=esc(user["lang"]),
            operator=esc(user["operator"] or "-"),
            panel=f"<code>{esc(panel['host'])}</code>" if panel else "-",
            builds=num(user["builds"], lang),
            banned=t(lang, "admin.on" if user["is_banned"] else "admin.off"),
            seen=ago(user["seen_at"], lang),
        )
        await message.answer(
            text, reply_markup=keyboards.admin_user(lang, user["tg_id"], bool(user["is_banned"]))
        )
        return

    listing = "\n".join(
        f"\u2022 <b>{esc(row['first_name'] or '-')}</b> \u00b7 @{esc(row['username'] or '-')} "
        f"\u00b7 <code>{num(row['tg_id'], lang)}</code>"
        for row in matches
    )
    await message.answer(listing, reply_markup=keyboards.simple_back(lang, "adm:users"))


@router.message(AdminFlow.broadcast, F.text)
async def on_broadcast(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        return
    await state.clear()
    body = message.html_text or message.text or ""
    recipients = await db.all_user_ids()

    sent = failed = 0
    for position, tg_id in enumerate(recipients, start=1):
        try:
            await message.bot.send_message(tg_id, body, disable_web_page_preview=True)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        if position % 25 == 0:
            await asyncio.sleep(1.0)

    await db.log_event("broadcast", message.from_user.id, f"sent={sent} failed={failed}")
    await message.answer(
        t(lang, "admin.broadcast_done", sent=num(sent, lang), failed=num(failed, lang)),
        reply_markup=keyboards.simple_back(lang, "adm:menu"),
    )


@router.message(AdminFlow.channel, F.text)
async def on_channel_add(message: Message, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        return
    raw = (message.text or "").strip()
    target: object = raw
    if raw.lstrip("-").isdigit():
        target = int(raw)
    elif not raw.startswith("@"):
        target = f"@{raw}"

    try:
        chat = await message.bot.get_chat(target)
        invite = chat.invite_link
        if not invite and chat.username:
            invite = f"https://t.me/{chat.username}"
        if not invite:
            invite = await message.bot.export_chat_invite_link(chat.id)
    except Exception as error:  # noqa: BLE001
        await message.answer(t(lang, "admin.channel_bad", reason=esc(error)))
        return

    await state.clear()
    await db.add_channel(str(chat.id), chat.title or str(chat.id), invite or "")
    await db.log_event("channel_added", message.from_user.id, str(chat.id))
    await message.answer(
        t(lang, "admin.channel_added", title=esc(chat.title or chat.id)),
        reply_markup=keyboards.simple_back(lang, "adm:channels"),
    )
