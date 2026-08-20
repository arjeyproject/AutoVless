"""Support desk: users write to the admin, the admin answers inside the bot.

User flow:   support home -> compose -> admins get a card with a reply button
Admin flow:  inbox -> ticket card -> reply / close / reopen
Everything stays in Telegram, nothing leaves the bot.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards
from ..config import settings
from ..i18n import normalise, num, t
from ..utils import ago, edit, esc

log = logging.getLogger("autovless.support")
router = Router(name="support")

MAX_BODY = 1500
COOLDOWN = 30
THREAD_LIMIT = 12
LIST_LIMIT = 12

STATE_KEYS = {
    db.TICKET_OPEN: "support_state_open",
    db.TICKET_ANSWERED: "support_state_answered",
    db.TICKET_CLOSED: "support_state_closed",
}


class SupportFlow(StatesGroup):
    compose = State()
    reply = State()


# --------------------------------------------------------------- helpers


def _state_label(lang: str, status: Optional[str]) -> str:
    return t(lang, STATE_KEYS.get(status or "", "support_state_none"))


def _who(ticket: dict) -> str:
    return str(ticket.get("first_name") or ticket.get("username") or ticket.get("tg_id") or "-")


def _lang_of(row: object) -> str:
    value = None
    if isinstance(row, dict):
        value = row.get("lang") or row.get("user_lang")
    elif row is not None:
        try:
            value = row["lang"]
        except (KeyError, IndexError, TypeError):
            value = None
    return normalise(value) if value else settings.default_lang


def render_thread(rows: list[dict], lang: str, user_label: Optional[str] = None) -> str:
    if not rows:
        return "-"
    blocks = []
    for row in rows:
        if row["sender"] == db.SENDER_ADMIN:
            who = t(lang, "support_admin")
        else:
            who = user_label or t(lang, "support_you")
        blocks.append(f"<b>{who}</b> \u00b7 {ago(row['at'], lang)}\n{esc(row['body'])}")
    return "\n\n".join(blocks)


async def notify_admins(message: Message, ticket_id: int, body: str) -> bool:
    """Push the incoming message to every admin. True if at least one got it."""
    author = message.from_user
    delivered = False
    for admin_id in settings.admin_ids:
        admin = await db.get_user(admin_id)
        alang = _lang_of(admin)
        text = t(
            alang,
            "support.new_ticket",
            name=esc(author.first_name or "-"),
            username=f"@{esc(author.username)}" if author.username else "-",
            tg_id=author.id,
            ticket=ticket_id,
            body=esc(body),
        )
        try:
            await message.bot.send_message(
                admin_id,
                text,
                reply_markup=keyboards.support_ticket(alang, ticket_id),
                disable_web_page_preview=True,
            )
            delivered = True
        except Exception as error:  # noqa: BLE001
            log.warning("could not deliver ticket %s to admin %s: %s", ticket_id, admin_id, error)
    return delivered


# ------------------------------------------------------------- user side


async def show_home(event: CallbackQuery | Message, lang: str) -> None:
    actor = event.from_user
    ticket = await db.latest_ticket(actor.id)
    count = await db.ticket_message_count(int(ticket["id"])) if ticket else 0
    note = (await db.get_option("support_note")).strip()
    text = t(
        lang,
        "support_menu",
        state=_state_label(lang, ticket["status"] if ticket else None),
        count=num(count, lang),
        note=f"\n\n\U0001f4cc {esc(note)}" if note else "",
    )
    await edit(event, text, keyboards.support_menu(lang, ticket is not None))


@router.callback_query(F.data == "nav:support")
async def on_support_home(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await show_home(call, lang)
    await call.answer()


@router.callback_query(F.data == "sup:new")
async def on_support_new(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not await db.get_flag("support_enabled"):
        await call.answer(t(lang, "support_off"), show_alert=True)
        return
    await state.set_state(SupportFlow.compose)
    await edit(
        call,
        t(lang, "support_prompt", limit=num(MAX_BODY, lang)),
        keyboards.simple_back(lang, "nav:support"),
    )
    await call.answer()


@router.callback_query(F.data == "sup:thread")
async def on_support_thread(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    ticket = await db.latest_ticket(call.from_user.id)
    if ticket is None:
        await edit(call, t(lang, "support_thread_empty"), keyboards.support_menu(lang, False))
        await call.answer()
        return
    ticket_id = int(ticket["id"])
    await db.mark_ticket_seen(ticket_id, db.SENDER_USER)
    thread = await db.ticket_thread(ticket_id, THREAD_LIMIT)
    await edit(
        call,
        t(lang, "support_thread", ticket=ticket_id, list=render_thread(thread, lang)),
        keyboards.support_menu(lang, True),
    )
    await call.answer()


@router.message(SupportFlow.compose, F.text, ~F.text.startswith("/"))
async def on_support_compose(
    message: Message,
    state: FSMContext,
    lang: str,
    is_admin: bool,
) -> None:
    body = (message.text or "").strip()

    if not await db.get_flag("support_enabled"):
        await state.clear()
        await message.answer(t(lang, "support_off"), reply_markup=keyboards.simple_back(lang))
        return
    if not body:
        await message.answer(t(lang, "support.empty_body"))
        return
    if len(body) > MAX_BODY:
        await message.answer(t(lang, "support_too_long", limit=num(MAX_BODY, lang)))
        return

    last = await db.last_support_message_at(message.from_user.id)
    if last and not is_admin and db.now() - last < COOLDOWN:
        await message.answer(t(lang, "support_too_fast", seconds=num(COOLDOWN, lang)))
        return

    await state.clear()
    ticket_id = await db.open_ticket(message.from_user.id)
    await db.add_ticket_message(ticket_id, db.SENDER_USER, body)
    await db.log_event("support", message.from_user.id, f"ticket={ticket_id}")

    if not await notify_admins(message, ticket_id, body):
        await message.answer(t(lang, "support_no_admin"))

    await message.answer(
        t(lang, "support_sent", ticket=ticket_id),
        reply_markup=keyboards.support_menu(lang, True),
    )


# ------------------------------------------------------------ admin side


async def show_inbox(call: CallbackQuery, lang: str, scope: str) -> None:
    stats = await db.ticket_stats()
    tickets = await db.tickets(scope, LIST_LIMIT)
    listing = "\n".join(
        f"{keyboards.TICKET_MARKS.get(str(ticket['status']), '\u2022')} "
        f"<b>#{ticket['id']}</b> \u00b7 {esc(_who(ticket))} \u00b7 {ago(ticket['updated_at'], lang)}"
        for ticket in tickets
    ) or t(lang, "support.list_empty")
    text = t(
        lang,
        "support.list",
        open=num(stats["open"], lang),
        answered=num(stats["answered"], lang),
        closed=num(stats["closed"], lang),
        waiting=num(stats["waiting"], lang),
        list=listing,
    )
    await edit(call, text, keyboards.support_list(lang, tickets, scope))


async def show_card(call: CallbackQuery, lang: str, ticket_id: int) -> None:
    ticket = await db.get_ticket(ticket_id)
    if ticket is None:
        await edit(call, t(lang, "support.gone"), keyboards.simple_back(lang, "sup:list:open"))
        return
    thread = await db.ticket_thread(ticket_id, THREAD_LIMIT)
    text = t(
        lang,
        "support.card",
        ticket=ticket_id,
        name=esc(ticket.get("first_name") or "-"),
        username=f"@{esc(ticket['username'])}" if ticket.get("username") else "-",
        tg_id=ticket["tg_id"],
        state=_state_label(lang, ticket["status"]),
        updated=ago(ticket["updated_at"], lang),
        list=render_thread(thread, lang, user_label=esc(_who(ticket))),
    )
    await edit(
        call,
        text,
        keyboards.support_ticket(lang, ticket_id, ticket["status"] == db.TICKET_CLOSED),
    )


@router.callback_query(F.data.startswith("sup:"))
async def on_admin_support(
    call: CallbackQuery,
    state: FSMContext,
    lang: str,
    is_admin: bool,
) -> None:
    if not is_admin:
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return

    parts = (call.data or "sup:list").split(":")
    action = parts[1] if len(parts) > 1 else "list"
    arg = parts[2] if len(parts) > 2 else ""

    if action == "list":
        await state.clear()
        await show_inbox(call, lang, arg or "open")
        await call.answer()
        return

    if action == "toggle":
        enabled = await db.toggle_flag("support_enabled")
        await db.log_event("support_toggle", call.from_user.id, "on" if enabled else "off")
        await call.answer(t(lang, "support.toggle_on" if enabled else "support.toggle_off"))
        await show_inbox(call, lang, "open")
        return

    if not arg.isdigit():
        await call.answer(t(lang, "support.gone"), show_alert=True)
        return
    ticket_id = int(arg)

    if action == "open":
        await db.mark_ticket_seen(ticket_id, db.SENDER_ADMIN)
        await show_card(call, lang, ticket_id)

    elif action == "reply":
        ticket = await db.get_ticket(ticket_id)
        if ticket is None:
            await call.answer(t(lang, "support.gone"), show_alert=True)
            return
        await state.set_state(SupportFlow.reply)
        await state.update_data(ticket_id=ticket_id)
        await edit(
            call,
            t(lang, "support.reply_prompt", name=esc(_who(ticket))),
            keyboards.simple_back(lang, f"sup:open:{ticket_id}"),
        )

    elif action in {"close", "reopen"}:
        closing = action == "close"
        await db.set_ticket_status(ticket_id, db.TICKET_CLOSED if closing else db.TICKET_OPEN)
        await db.log_event(f"support_{action}", call.from_user.id, f"ticket={ticket_id}")
        if closing:
            ticket = await db.get_ticket(ticket_id)
            if ticket is not None:
                tlang = _lang_of(ticket)
                try:
                    await call.bot.send_message(
                        ticket["tg_id"],
                        t(tlang, "support_closed_user", ticket=ticket_id),
                        reply_markup=keyboards.support_user_reply(tlang),
                    )
                except Exception as error:  # noqa: BLE001
                    log.warning("close notice failed for ticket %s: %s", ticket_id, error)
        await call.answer(t(lang, "support.closed" if closing else "support.reopened"))
        await show_card(call, lang, ticket_id)
        return

    await call.answer()


@router.message(SupportFlow.reply, F.text, ~F.text.startswith("/"))
async def on_admin_reply(
    message: Message,
    state: FSMContext,
    lang: str,
    is_admin: bool,
) -> None:
    if not is_admin:
        await state.clear()
        return

    data = await state.get_data()
    raw_id = data.get("ticket_id")
    ticket = await db.get_ticket(int(raw_id)) if raw_id else None
    if ticket is None:
        await state.clear()
        await message.answer(t(lang, "support.gone"), reply_markup=keyboards.simple_back(lang, "sup:list:open"))
        return

    ticket_id = int(ticket["id"])
    plain = (message.text or "").strip()
    if not plain:
        await message.answer(t(lang, "support.empty_body"))
        return
    body = message.html_text or plain
    tlang = _lang_of(ticket)

    try:
        await message.bot.send_message(
            ticket["tg_id"],
            t(tlang, "support_incoming", body=body, ticket=ticket_id),
            reply_markup=keyboards.support_user_reply(tlang),
            disable_web_page_preview=True,
        )
    except Exception as error:  # noqa: BLE001
        log.warning("reply to ticket %s failed: %s", ticket_id, error)
        await message.answer(t(lang, "support.reply_failed", reason=esc(error)))
        return

    await state.clear()
    await db.add_ticket_message(ticket_id, db.SENDER_ADMIN, plain, message.from_user.id)
    await db.log_event("support_reply", message.from_user.id, f"ticket={ticket_id}")
    await message.answer(
        t(lang, "support.reply_sent", name=esc(_who(ticket))),
        reply_markup=keyboards.support_ticket(lang, ticket_id),
    )
