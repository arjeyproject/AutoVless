"""Apps and downloads: a platform picker, then real store links.

The old screen was a wall of app names with nothing to tap. Here each app is an
inline URL button, so one tap opens Google Play, the App Store or the project's
release page. Nothing is a dead end and nothing needs copying by hand.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import apps as catalogue
from .. import keyboards
from ..i18n import num, t
from ..utils import edit

router = Router(name="apps")

ICONS = {
    "android": "\U0001f916",
    "ios": "\uf8ff",
    "windows": "\U0001fa9f",
    "macos": "\U0001f4bb",
    "linux": "\U0001f427",
}


def platform_screen(lang: str, platform: str, tag: str = "") -> tuple[str, object]:
    items = catalogue.listing(platform, tag)
    text = t(
        lang,
        "apps.platform",
        icon=ICONS.get(platform, "\U0001f4f1"),
        title=t(lang, f"apps.title_{platform}"),
        count=num(len(items), lang),
        note=t(lang, f"apps.note_{platform}"),
    )
    return text, keyboards.apps_list(lang, platform, tag)


@router.callback_query(F.data == "nav:apps")
async def on_apps(call: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await edit(call, t(lang, "apps.home"), keyboards.apps_platforms(lang))
    await call.answer()


@router.message(Command("apps"))
async def on_apps_command(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(
        t(lang, "apps.home"),
        reply_markup=keyboards.apps_platforms(lang),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("apps:"))
async def on_platform(call: CallbackQuery, lang: str) -> None:
    parts = (call.data or "").split(":")
    platform = parts[1] if len(parts) > 1 else ""
    tag = parts[2] if len(parts) > 2 else ""

    if platform not in catalogue.PLATFORMS:
        await edit(call, t(lang, "apps.home"), keyboards.apps_platforms(lang))
        await call.answer()
        return

    text, markup = platform_screen(lang, platform, tag)
    await edit(call, text, markup)
    await call.answer()
