"""Admin screens added in 2.0: the invite lock, the free pool, the AI route.

This router is included *before* ``handlers.admin`` on purpose. That module owns
one broad ``adm:`` handler, so the only way to add a screen without rewriting it
is to claim the specific callbacks first - including ``adm:menu``, because the
admin home needs three more buttons and the keyboard is built there.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import aipin, db, freepool, keyboards, proxies, store
from ..i18n import num, t
from ..utils import ago, edit, esc

log = logging.getLogger("autovless.handlers.adminx")
router = Router(name="adminx")

MAX_REQUIRED = 50


class AdminXFlow(StatesGroup):
    referral_count = State()
    free_server = State()


def _b(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def _state(lang: str, value: bool) -> str:
    return t(lang, "admin.on" if value else "admin.off")


def admin_home(lang: str) -> InlineKeyboardMarkup:
    """The stock admin keyboard plus the three new screens."""
    markup = keyboards.admin_menu(lang)
    rows = list(markup.inline_keyboard)
    extra = [
        [_b(t(lang, "btn.ref_lock"), "adm:ref"), _b(t(lang, "btn.free_admin"), "adm:free")],
        [_b(t(lang, "btn.ai_relays"), "adm:ai")],
    ]
    insert_at = max(0, len(rows) - 1)
    for row in reversed(extra):
        rows.insert(insert_at, row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def referral_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.ref_toggle"), "adm:ref:toggle")],
            [_b(t(lang, "btn.ref_count"), "adm:ref:count"), _b(t(lang, "btn.ref_top"), "adm:ref:top")],
            [_b(t(lang, "btn.back"), "adm:menu")],
        ]
    )


def free_menu(lang: str, servers: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for server in servers[:10]:
        mark = "\u2705" if server.get("healthy") else "\u26a0\ufe0f"
        if not server.get("active"):
            mark = "\u26aa\ufe0f"
        rows.append(
            [
                _b(f"{mark} {server['host'][:26]}", f"adm:free:toggle:{server['id']}"),
                _b("\U0001f5d1", f"adm:free:del:{server['id']}"),
            ]
        )
    rows.append([_b(t(lang, "btn.free_add"), "adm:free:add"), _b(t(lang, "btn.free_from_panel"), "adm:free:panel")])
    rows.append([_b(t(lang, "btn.free_check"), "adm:free:check")])
    rows.append([_b(t(lang, "btn.back"), "adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ai_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.ai_geo"), "adm:ai:geo")],
            [_b(t(lang, "btn.back"), "adm:menu")],
        ]
    )


def _guard(is_admin: bool) -> bool:
    return bool(is_admin)


# --------------------------------------------------------------------- home


@router.callback_query(F.data == "adm:menu")
async def on_home(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
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
        maintenance=_state(lang, await db.get_flag("maintenance")),
        builds=_state(lang, await db.get_flag("builds_enabled")),
    )
    await edit(call, text, admin_home(lang))
    await call.answer()


# ----------------------------------------------------------------- referral


async def show_referral(call: CallbackQuery, lang: str) -> None:
    stats = await store.referral_stats()
    text = t(
        lang,
        "admin.ref",
        state=_state(lang, bool(stats["locked"])),
        required=num(stats["required"], lang),
        total=num(stats["total"], lang),
        today=num(stats["today"], lang),
        inviters=num(stats["inviters"], lang),
    )
    await edit(call, text, referral_menu(lang))


@router.callback_query(F.data == "adm:ref")
async def on_referral(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
    await show_referral(call, lang)
    await call.answer()


@router.callback_query(F.data == "adm:ref:toggle")
async def on_referral_toggle(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await store.ensure()
    state = await db.toggle_flag("referral_lock")
    await db.log_event("option", call.from_user.id, f"referral_lock={state}")
    await show_referral(call, lang)
    await call.answer(t(lang, "admin.saved"))


@router.callback_query(F.data == "adm:ref:count")
async def on_referral_count(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.set_state(AdminXFlow.referral_count)
    await edit(call, t(lang, "admin.ref_prompt"), keyboards.simple_back(lang, "adm:ref"))
    await call.answer()


@router.message(AdminXFlow.referral_count, F.text)
async def on_referral_count_set(
    message: Message, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t(lang, "admin.ref_bad"))
        return
    value = max(0, min(MAX_REQUIRED, int(raw)))
    await state.clear()
    await store.set_int("referral_required", value)
    await db.log_event("option", message.from_user.id, f"referral_required={value}")
    await message.answer(
        t(lang, "admin.ref_saved", required=num(value, lang)),
        reply_markup=keyboards.simple_back(lang, "adm:ref"),
    )


@router.callback_query(F.data == "adm:ref:top")
async def on_referral_top(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    rows = await store.referral_top(10)
    listing = "\n".join(
        f"{index}. <b>{esc(row.get('first_name') or '-')}</b> \u00b7 "
        f"@{esc(row.get('username') or '-')} \u00b7 <b>{num(row['invites'], lang)}</b>"
        for index, row in enumerate(rows, start=1)
    ) or t(lang, "admin.ref_empty")
    await edit(call, t(lang, "admin.ref_top", list=listing), keyboards.simple_back(lang, "adm:ref"))
    await call.answer()


# --------------------------------------------------------------------- free


async def show_free(call: CallbackQuery, lang: str) -> None:
    servers = await store.free_servers(active_only=False)
    stats = await store.free_stats()
    lines = []
    for row in servers:
        mark = "\u2705" if row.get("healthy") else "\u26a0\ufe0f"
        if not row.get("active"):
            mark = "\u26aa\ufe0f"
        lines.append(
            f"\u2022 {mark} <code>{esc(row['host'])}</code>\n"
            f"  \U0001f4e6 {num(row.get('hits') or 0, lang)} \u00b7 {ago(row.get('checked_at') or 0, lang)}"
        )
    listing = "\n".join(lines) or t(lang, "admin.free_empty")
    text = t(
        lang,
        "admin.free",
        servers=num(stats["servers"], lang),
        healthy=num(stats["healthy"], lang),
        grants=num(stats["grants"], lang),
        users=num(stats["users"], lang),
        list=listing,
    )
    await edit(call, text, free_menu(lang, servers))


@router.callback_query(F.data == "adm:free")
async def on_free(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.clear()
    await show_free(call, lang)
    await call.answer()


@router.callback_query(F.data == "adm:free:add")
async def on_free_add(call: CallbackQuery, state: FSMContext, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await state.set_state(AdminXFlow.free_server)
    await edit(call, t(lang, "admin.free_prompt"), keyboards.simple_back(lang, "adm:free"))
    await call.answer()


@router.message(AdminXFlow.free_server, F.text)
async def on_free_server_input(
    message: Message, state: FSMContext, lang: str, is_admin: bool
) -> None:
    if not _guard(is_admin):
        return
    try:
        row = await freepool.add((message.text or "").strip())
    except ValueError as error:
        await message.answer(t(lang, "admin.free_bad", reason=esc(error)))
        return
    await state.clear()
    await db.log_event("free_server", message.from_user.id, row["host"])
    await message.answer(
        t(lang, "admin.free_added", host=esc(row["host"])),
        reply_markup=keyboards.simple_back(lang, "adm:free"),
    )


@router.callback_query(F.data == "adm:free:panel")
async def on_free_from_panel(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    row = await freepool.add_from_panel(call.from_user.id)
    if row is None:
        await call.answer(t(lang, "admin.free_panel_none"), show_alert=True)
        return
    await show_free(call, lang)
    await call.answer(t(lang, "admin.free_added", host=row["host"]).replace("<code>", "").replace("</code>", ""))


@router.callback_query(F.data == "adm:free:check")
async def on_free_check(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await call.answer()
    healthy, total = await freepool.check_all()
    await show_free(call, lang)
    await call.message.answer(
        t(lang, "admin.free_checked", healthy=num(healthy, lang), total=num(total, lang))
    )


@router.callback_query(F.data.startswith("adm:free:toggle:"))
async def on_free_toggle(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    server_id = (call.data or "").rsplit(":", 1)[-1]
    if server_id.isdigit():
        await store.toggle_free_server(int(server_id))
    await show_free(call, lang)
    await call.answer(t(lang, "admin.saved"))


@router.callback_query(F.data.startswith("adm:free:del:"))
async def on_free_delete(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    server_id = (call.data or "").rsplit(":", 1)[-1]
    if server_id.isdigit():
        await store.remove_free_server(int(server_id))
    await show_free(call, lang)
    await call.answer(t(lang, "admin.free_gone"))


# ----------------------------------------------------------------------- ai


async def show_ai(call: CallbackQuery, lang: str) -> None:
    report = await aipin.report()
    relays = report["relays"]
    pins = report["pins"]
    countries = " \u00b7 ".join(
        f"{code} ({num(hits, lang)})" for code, hits in relays.get("countries") or []
    ) or "-"
    spread = " \u00b7 ".join(
        f"{code} ({num(hits, lang)})" for code, hits in pins.get("countries") or []
    ) or "-"
    text = t(
        lang,
        "admin.ai",
        verified=num(relays["verified"], lang),
        total=num(relays["total"], lang),
        placed=num(relays["placed"], lang),
        us=num(relays["us"], lang),
        countries=countries,
        pinned=num(pins["pinned"], lang),
        pins=spread,
        domains=num(report["domains"], lang),
    )
    await edit(call, text, ai_menu(lang))


@router.callback_query(F.data == "adm:ai")
async def on_ai(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await show_ai(call, lang)
    await call.answer()


@router.callback_query(F.data == "adm:ai:geo")
async def on_ai_geo(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    """Place every relay we hold. One tap, and the AI pin has somewhere to go."""
    if not _guard(is_admin):
        await call.answer(t(lang, "admin.denied"), show_alert=True)
        return
    await call.answer()
    notice = await call.message.answer(t(lang, "admin.ai_geo"))
    rows = await proxies.best(60, verified_only=False)
    await proxies.ensure_countries([row["host"] for row in rows])
    stats = await proxies.stats()
    await notice.edit_text(
        t(lang, "admin.ai_geo_done", placed=num(stats["placed"], lang), us=num(stats["us"], lang))
    )
    await show_ai(call, lang)
