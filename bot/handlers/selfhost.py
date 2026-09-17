"""The free, automatic tier: VLESS-REALITY and Shadowsocks-2022 from your box.

Additive by design. This router claims one command and one callback prefix
(``sh:``) and touches nothing the panel flow owns, so it cannot change the
behaviour of anything that already works.
"""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import selfhost
from ..config import settings

log = logging.getLogger("autovless.handlers.selfhost")
router = Router(name="selfhost")

LABELS = {"\U0001f3e0 سرور خودم", "\U0001f3e0 Self-host"}


def _lang(lang: str) -> str:
    lang = str(lang or "").lower()
    return lang if lang in {"fa", "en"} else settings.default_lang


def _keyboard(lang: str) -> InlineKeyboardMarkup:
    sub = "\U0001f4e6 Subscription" if lang == "en" else "\U0001f4e6 لینک اشتراک"
    sing = "\u2699\ufe0f sing-box" if lang == "en" else "\u2699\ufe0f فایل sing-box"
    clash = "\u2699\ufe0f Clash" if lang == "en" else "\u2699\ufe0f فایل Clash"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=sub, callback_data="sh:sub")],
            [
                InlineKeyboardButton(text=sing, callback_data="sh:singbox"),
                InlineKeyboardButton(text=clash, callback_data="sh:clash"),
            ],
        ]
    )


def _offline(lang: str) -> str:
    if lang == "en":
        return (
            "\u26a0\ufe0f The self-hosted node is not configured yet.\n\n"
            "Run <code>scripts/install-selfhost.sh</code> on your VPS, paste the block "
            "it prints into <code>.env</code>, then restart the bot."
        )
    return (
        "\u26a0\ufe0f نود اختصاصی هنوز تنطیم نشده.\n\n"
        "روی سرور مجازی‌ات <code>scripts/install-selfhost.sh</code> را اجرا کن، "
        "بلوکی که چاپ می‌کند را در <code>.env</code> بگذار و ربات را ری‌استارت کن."
    )


def _body(tg_id: int, lang: str) -> str:
    node = selfhost.load()
    head = (
        "\U0001f3e0 <b>Free tier - your own server</b>\n"
        "No Cloudflare account in the path, so there is nothing to suspend.\n\n"
        if lang == "en"
        else "\U0001f3e0 <b>سرویس رایگان روی سرور خودت</b>\n"
        "هیچ اکانت کلادفلری در مسیر نیست، پس چیزی برای ساسپند شدن وجود ندارد.\n\n"
    )
    facts = ""
    if node.reality_ready:
        facts += (
            f"\u26a1 VLESS-REALITY \u00b7 <code>{node.host}:{node.reality_port}</code> "
            f"\u00b7 SNI <code>{node.reality_sni}</code>\n"
        )
    if node.ss_ready:
        facts += (
            f"\U0001f512 Shadowsocks-2022 \u00b7 <code>{node.host}:{node.ss_port}</code> "
            f"\u00b7 <code>{node.ss_method}</code>\n"
        )
    body = "\n".join(f"<code>{link}</code>" for link in selfhost.links(tg_id))
    return head + facts + "\n" + body


@router.message(Command("selfhost"))
async def on_command(message: Message, lang: str = "") -> None:
    await _send(message, _lang(lang))


@router.message(F.text.in_(LABELS))
async def on_button(message: Message, lang: str = "") -> None:
    await _send(message, _lang(lang))


async def _send(message: Message, lang: str) -> None:
    if message.from_user is None:
        return
    if not selfhost.enabled():
        await message.answer(_offline(lang))
        return
    await message.answer(_body(message.from_user.id, lang), reply_markup=_keyboard(lang))


@router.callback_query(F.data.startswith("sh:"))
async def on_callback(call: CallbackQuery, lang: str = "") -> None:
    lang = _lang(lang)
    if call.from_user is None or call.message is None:
        await call.answer()
        return
    if not selfhost.enabled():
        await call.answer("not configured" if lang == "en" else "تنطیم نشده", show_alert=True)
        return

    tg_id = call.from_user.id
    action = str(call.data or "")[3:]

    if action == "sub":
        text = f"<code>{selfhost.subscription(tg_id)}</code>"
    elif action == "singbox":
        payload = {"outbounds": selfhost.singbox_outbounds(tg_id)}
        text = "<pre>" + json.dumps(payload, indent=2, ensure_ascii=False) + "</pre>"
    elif action == "clash":
        text = "<pre>proxies:\n" + "\n".join(selfhost.clash_proxies(tg_id)) + "</pre>"
    else:
        await call.answer()
        return

    try:
        await call.message.answer(text)
    except Exception:  # noqa: BLE001
        log.exception("could not deliver self-host export %s", action)
        await call.answer("failed" if lang == "en" else "ناموفق بود", show_alert=True)
        return
    await call.answer()
