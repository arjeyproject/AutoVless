"""Small shared helpers."""

from __future__ import annotations

import asyncio
import html
import time
from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .i18n import num

# Right-to-left mark. Telegram lays a line out by its first strong character, so
# a line that starts with an emoji or a latin word drifts to the left and the
# whole Persian screen looks broken. Starting the line with this fixes it.
RLM = "\u200f"

_AGO_UNITS = {
    "now": {"fa": "\u0644\u062d\u0637\u0647\u200c\u0627\u06cc \u067e\u06cc\u0634", "en": "just now"},
    "min": {"fa": "\u062f\u0642\u06cc\u0642\u0647 \u067e\u06cc\u0634", "en": "min ago"},
    "hour": {"fa": "\u0633\u0627\u0639\u062a \u067e\u06cc\u0634", "en": "h ago"},
    "day": {"fa": "\u0631\u0648\u0632 \u067e\u06cc\u0634", "en": "d ago"},
}


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def rtl(text: str, lang: str) -> str:
    """Prefix every line with an RLM so a Persian screen stays right aligned."""
    if lang != "fa":
        return text
    return "\n".join(
        line if not line or line.startswith(RLM) else f"{RLM}{line}"
        for line in text.split("\n")
    )


def _unit(key: str, lang: str) -> str:
    return _AGO_UNITS[key]["en" if lang == "en" else "fa"]


def ago(timestamp: Optional[int], lang: str) -> str:
    """Relative time, in the reader's language and numerals."""
    if not timestamp:
        return "-"
    delta = max(0, int(time.time()) - int(timestamp))
    if delta < 60:
        return _unit("now", lang)
    if delta < 3600:
        return f"{num(delta // 60, lang)} {_unit('min', lang)}"
    if delta < 86_400:
        return f"{num(delta // 3600, lang)} {_unit('hour', lang)}"
    return f"{num(delta // 86_400, lang)} {_unit('day', lang)}"


def ping_label(latency: Optional[float], lang: str) -> str:
    if not latency:
        return "-"
    return f"{num(round(float(latency)), lang)} ms"


async def edit(
    event: CallbackQuery | Message,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Edit in place for a callback, send fresh for a command.

    A message that arrived from the user cannot be edited by the bot, so trying
    always failed and quietly fell through to a second send.
    """
    if isinstance(event, Message):
        await event.answer(text, reply_markup=markup, disable_web_page_preview=True)
        return

    message = event.message
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
