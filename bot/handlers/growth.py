"""The three screens added in 2.0 on the user's side.

* ``nav:invite`` the invite card, and the recheck button the lock screen offers
* ``nav:free``   free configs, built on a shared worker by the real engine
* ``nav:miniapp`` the Web App button

This router is registered ahead of the older ones so its ``nav:`` callbacks are
seen first, and nothing in ``keyboards.py`` or ``handlers/admin.py`` had to be
touched to add them.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import db, freepool, keyboards, referral, screens, store
from ..config import settings
from ..i18n import num, t
from ..utils import chunked, edit, esc, ping_label
from ..webapp import build_webapp_url
from .webapp import miniapp_keyboard

log = logging.getLogger("autovless.handlers.growth")
router = Router(name="growth")

TIPS = {"vless": "free.tip_vless", "trojan": "free.tip_trojan", "mix": "free.tip_mix"}
TITLES = {"vless": "btn.free_vless", "trojan": "btn.free_trojan", "mix": "btn.free_mix"}


def _b(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def free_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b(t(lang, "btn.free_vless"), "free:vless"), _b(t(lang, "btn.free_trojan"), "free:trojan")],
            [_b(t(lang, "btn.free_mix"), "free:mix")],
            [_b(t(lang, "btn.free_warp"), "nav:warp")],
            [_b(t(lang, "btn.apps"), "nav:apps")],
            [_b(t(lang, "btn.back"), "nav:menu")],
        ]
    )


# --------------------------------------------------------------------- invite


@router.message(Command("invite"))
async def on_invite_command(message: Message, lang: str) -> None:
    body, markup = await referral.card(message.bot, message.from_user.id, lang)
    await message.answer(body, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "nav:invite")
async def on_invite(call: CallbackQuery, lang: str) -> None:
    body, markup = await referral.card(call.bot, call.from_user.id, lang)
    await edit(call, body, markup)
    await call.answer()


@router.callback_query(F.data == "ref:check")
async def on_invite_check(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    if await referral.unlocked(call.from_user.id, is_admin):
        name = call.from_user.first_name or ""
        text, markup = await screens.main_menu(name, lang, is_admin)
        await edit(call, text, markup)
        await call.answer(t(lang, "ref.checked_ok"), show_alert=True)
        return
    goal = await referral.required()
    done = await referral.invited(call.from_user.id)
    await call.answer(t(lang, "ref.checked_no", left=num(max(0, goal - done), lang)), show_alert=True)


# ----------------------------------------------------------------- free pool


@router.callback_query(F.data == "nav:free")
async def on_free(call: CallbackQuery, lang: str) -> None:
    if not await store.flag("free_enabled", True):
        await edit(call, t(lang, "free.disabled"), keyboards.simple_back(lang))
        await call.answer()
        return

    stats = await freepool.stats()
    if not stats["servers"]:
        await edit(call, t(lang, "free.none"), keyboards.simple_back(lang))
        await call.answer()
        return

    body = t(
        lang,
        "free.menu",
        servers=num(stats["servers"], lang),
        verified=num(stats["verified"], lang),
        warp=num(stats["warp"], lang),
    )
    await edit(call, body, free_menu(lang))
    await call.answer()


@router.callback_query(F.data.startswith("free:"))
async def on_free_build(call: CallbackQuery, lang: str, is_admin: bool) -> None:
    protocol = (call.data or "free:vless").split(":", 1)[1]
    if protocol not in freepool.PROTOCOLS:
        await call.answer()
        return

    if not await store.flag("free_enabled", True):
        await call.answer(t(lang, "free.disabled"), show_alert=True)
        return

    allowed, limit = await freepool.allowed(call.from_user.id, is_admin)
    if not allowed:
        await call.answer(t(lang, "free.limit", limit=num(limit, lang)), show_alert=True)
        return

    await call.answer()
    notice = await call.message.answer(t(lang, "free.building"))

    try:
        result = await freepool.build(call.from_user.id, protocol)
    except Exception:  # noqa: BLE001
        log.exception("free build failed")
        await notice.edit_text(t(lang, "free.empty"))
        return

    if result is None:
        await notice.edit_text(t(lang, "free.empty"))
        return

    header = t(
        lang,
        "free.ready",
        title=t(lang, TITLES.get(protocol, "btn.free")),
        host=esc(result["host"]),
        count=num(result["count"], lang),
        best=ping_label(result["best"], lang),
        sub=esc(result["sub"]),
        tip=t(lang, TIPS.get(protocol, "free.tip_vless")),
    )
    body = header + "\n\n" + "\n\n".join(
        f"<b>#{num(index, lang)}</b>\n<code>{esc(link)}</code>"
        for index, link in enumerate(result["links"], start=1)
    )

    await notice.delete()
    parts = chunked(body)
    for position, part in enumerate(parts):
        last = position == len(parts) - 1
        await call.message.answer(
            part,
            reply_markup=free_menu(lang) if last else None,
            disable_web_page_preview=True,
        )
    await db.log_event("free", call.from_user.id, f"{protocol} links={result['count']}")


# ------------------------------------------------------------------ mini app


@router.callback_query(F.data == "nav:miniapp")
async def on_miniapp(call: CallbackQuery, lang: str) -> None:
    if not settings.webapp_url.strip():
        await call.answer("WEBAPP_URL", show_alert=True)
        return
    await call.answer()
    try:
        url = await build_webapp_url(call.from_user.id, lang)
    except Exception:  # noqa: BLE001
        log.exception("could not build the mini app url")
        await call.message.answer(
            "Could not build the mini app link." if lang == "en" else "\u0633\u0627\u062e\u062a \u0644\u06cc\u0646\u06a9 \u0645\u06cc\u0646\u06cc\u200c\u0627\u067e \u0646\u0627\u0645\u0648\u0641\u0642 \u0628\u0648\u062f."
        )
        return
    await call.message.answer(
        t(lang, "miniapp.card", brand=esc(settings.brand)),
        reply_markup=miniapp_keyboard(url, lang),
    )
