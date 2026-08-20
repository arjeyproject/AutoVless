"""Small shared helpers."""

from __future__ import annotations

import asyncio
import html
import time
from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .i18n import num, t


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=False)


def ago(timestamp: Optional[int], lang: str) -> str:
    if not timestamp:
        return "-"
    delta = max(0, int(time.time()) - int(timestamp))
    if delta < 60:
        return t(lang, "time.now") if False else ("just now" if lang == "en" else "\u0644\u062d\u0637\u0647\u200c\u0627\u06cc \u067e\u06cc\u0634")
    if delta < 3600:
        value = num(delta // 60, lang)
        return f"{value} min" if lang == "en" else f"{value} \u062f\u0642\u06cc\u0642\u0647 \u067e\u06cc\u0634"
    if delta < 86_400:
        value = num(delta // 3600, lang)
        return f"{value} h" if lang == "en" else f"{value} \u0633\u0627\u0639\u062a \u067e\u06cc\u0634"
    value = num(delta // 86_400, lang)
    return f"{value} d" if lang == "en" else f"{value} \u0631\u0648\u0632 \u067e\u06cc\u0634"


def ping_label(latency: Optional[float], lang: str) -> str:
    if not latency:
        return "-"
    return f"{num(round(float(latency)), lang)} ms"


async def edit(
    event: CallbackQuery | Message,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Edit in place when possible, otherwise send a new message."""
    message = event.message if isinstance(event, CallbackQuery) else event
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return
        await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def tcp_latency(host: str, port: int, timeout: float = 2.0) -> Optional[float]:
    """Round-trip time of a TCP handshake, in milliseconds."""
    start = time.perf_counter()
    writer = None
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
    except (OSError, asyncio.TimeoutError):
        return None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):
                pass
    return (time.perf_counter() - start) * 1000


def chunked(text: str, size: int = 3500) -> list[str]:
    """Split long text on line boundaries so Telegram never rejects it."""
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > size:
            parts.append(current)
            current = line
        else:
            current += line
    if current:
        parts.append(current)
    return parts
