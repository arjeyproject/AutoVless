"""Telegram Mini App bridge.

/app hands the user a Web App button, and whatever the mini app sends back with
sendData() lands in on_webapp_data. Actions that destroy something are never
run from here: the mini app can only ask, the bot menu still confirms.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from .. import db
from ..config import settings
from ..webapp import build_webapp_url

log = logging.getLogger("autovless.handlers.webapp")
router = Router(name="webapp")

OPEN_LABELS = {"\U0001f680 مینی‌اپ", "\U0001f680 Mini App"}


def _lang(lang: str) -> str:
    lang = str(lang or "").lower()
    return lang if lang in {"fa", "en"} else settings.default_lang


def miniapp_keyboard(url: str, lang: str) -> ReplyKeyboardMarkup:
    label = "\U0001f680 Mini App" if lang == "en" else "\U0001f680 مینی‌اپ"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label, web_app=WebAppInfo(url=url))]],
        resize_keyboard=True,
        is_persistent=True,
    )


async def _run(module: str, attr: str, *methods: str, **kwargs) -> bool:
    """Call the first method that exists on an engine object. Never raises."""
    try:
        loaded = importlib.import_module(f"..{module}", __package__)
    except Exception:
        return False
    target = getattr(loaded, attr, None)
    if target is None:
        return False
    for name in methods:
        fn = getattr(target, name, None)
        if fn is None:
            continue
        try:
            result = fn(**kwargs)
            if inspect.isawaitable(result):
                await result
            return True
        except Exception:
            log.exception("mini app action failed: %s.%s", attr, name)
            return False
    return False


@router.message(Command("app"))
async def on_app_command(message: Message, lang: str = "") -> None:
    await _open(message, _lang(lang))


@router.message(F.text.in_(OPEN_LABELS))
async def on_app_button(message: Message, lang: str = "") -> None:
    await _open(message, _lang(lang))


async def _open(message: Message, lang: str) -> None:
    if not settings.webapp_url.strip():
        await message.answer(
            "WEBAPP_URL is not set in .env"
            if lang == "en"
            else "اول WEBAPP_URL را در فایل .env تنطیم کن."
        )
        return
    try:
        url = await build_webapp_url(message.from_user.id, lang)
    except Exception:
        log.exception("failed to build mini app url")
        await message.answer(
            "Could not build the mini app link." if lang == "en" else "ساخت لینک مینی‌اپ ناموفق بود."
        )
        return
    await message.answer(
        "Mini App is ready." if lang == "en" else "مینی‌اپ آماده است. دکمه‌ی پایین را بزن.",
        reply_markup=miniapp_keyboard(url, lang),
    )


@router.message(F.web_app_data)
async def on_webapp_data(message: Message, lang: str = "") -> None:
    lang = _lang(lang)
    raw = message.web_app_data.data if message.web_app_data else ""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        await message.answer("\u274c payload نامعتبر" if lang == "fa" else "\u274c bad payload")
        return
    if not isinstance(data, dict):
        await message.answer("\u274c payload نامعتبر" if lang == "fa" else "\u274c bad payload")
        return

    action = str(data.get("type") or "")
    tg_id = message.from_user.id

    try:
        await db.log_event("miniapp", tg_id, action[:100])
    except Exception:
        pass

    if action == "panel_apply":
        ok = await _run("autopilot", "autopilot", "refresh_panel", tg_id=tg_id, force_scan=True)
        if not ok:
            ok = await _run("autopilot", "autopilot", "run_once", "tick", "sync")
        await message.answer(
            ("\u2705 اعمال شد" if ok else "\u26a0\ufe0f از منوی پنل دکمه‌ی اعمال را بزن")
            if lang == "fa"
            else ("\u2705 Applied" if ok else "\u26a0\ufe0f Use the Apply button in the panel menu")
        )
        return

    if action == "panel_rescan":
        ok = await _run("scanner", "scanner", "scan_once", "run_once", "scan")
        await message.answer(
            ("\U0001f50d اسکن شروع شد" if ok else "\u26a0\ufe0f اسکنر در دسترس نیست")
            if lang == "fa"
            else ("\U0001f50d Scan started" if ok else "\u26a0\ufe0f Scanner is unavailable")
        )
        return

    if action == "warp_rescan":
        ok = await _run("warpscan", "warp_scanner", "scan_once", "run_once", "scan")
        await message.answer(
            ("\U0001f300 اسکن WARP شروع شد" if ok else "\u26a0\ufe0f اسکنر WARP در دسترس نیست")
            if lang == "fa"
            else ("\U0001f300 WARP scan started" if ok else "\u26a0\ufe0f WARP scanner is unavailable")
        )
        return

    if action == "save_settings":
        payload = data.get("payload") or {}
        new_lang = str(payload.get("lang") or "").lower()
        if new_lang in {"fa", "en"}:
            try:
                await db.set_lang(tg_id, new_lang)
                lang = new_lang
            except Exception:
                log.debug("could not persist language from mini app", exc_info=True)
        await message.answer(
            "\u2705 تنطیمات دریافت شد. تعداد کانفیگ از روی .env خوانده می‌شود."
            if lang == "fa"
            else "\u2705 Settings received. Config counts still come from .env."
        )
        return

    if action in {"panel_rebuild", "panel_ping", "panel_delete_request", "warp_build"}:
        await message.answer(
            "\u2139\ufe0f این اکشن تایید می‌خواهد. با /menu از داخل ربات ادامه بده."
            if lang == "fa"
            else "\u2139\ufe0f That action needs a confirmation. Continue from /menu inside the bot."
        )
        return

    await message.answer("\u2753 اکشن ناشناخته" if lang == "fa" else "\u2753 Unknown action")
