"""Screen composition shared by several handlers.

``main_menu`` grows one row here rather than in ``keyboards.py``: the free
config screen and the invite card are optional features an admin can switch off.
"""

from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import db, keyboards, operators, store
from .autopilot import autopilot
from .config import settings
from .i18n import num, t
from .scanner import proxy_scanner, scanner
from .utils import ago, esc, ping_label


def _button(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


async def _extra_rows(lang: str) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    if await store.flag("free_enabled", True):
        pair.append(_button(t(lang, "btn.free"), "nav:free"))
    pair.append(_button(t(lang, "btn.invite"), "nav:invite"))
    rows.append(pair)
    return rows


async def main_menu(name: str, lang: str, is_admin: bool) -> tuple[str, object]:
    stats = await scanner.stats()
    relays = await proxy_scanner.stats()
    pilot = await autopilot.stats()
    text = t(
        lang,
        "main_menu",
        brand=esc(settings.brand),
        name=esc(name or settings.brand),
        pool=num(stats["total"], lang),
        verified=num(stats["verified"], lang),
        fast=num(stats["fast"], lang),
        best=ping_label(stats["best"], lang),
        domains=num(stats["domains"], lang),
        relays=num(relays["verified"], lang),
        pilot=t(lang, "admin.on" if pilot["enabled"] else "admin.off"),
    )

    markup = keyboards.main_menu(lang, is_admin)
    rows = list(markup.inline_keyboard)
    # Above the language row and the admin button, below everything else.
    insert_at = max(0, len(rows) - (2 if is_admin else 1))
    for extra in reversed(await _extra_rows(lang)):
        rows.insert(insert_at, extra)
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def network_status(lang: str) -> tuple[str, object]:
    stats = await scanner.stats()
    relays = await proxy_scanner.stats()
    pilot = await autopilot.stats()
    rows = await db.fetch_all(
        "SELECT colo, COUNT(*) AS hits FROM clean_ips WHERE colo IS NOT NULL "
        "GROUP BY colo ORDER BY hits DESC LIMIT 6"
    )
    colos = " · ".join(f"{esc(row['colo'])} ({num(row['hits'], lang)})" for row in rows) or "-"
    text = t(
        lang,
        "network_status",
        total=num(stats["total"], lang),
        verified=num(stats["verified"], lang),
        fast=num(stats["fast"], lang),
        best=ping_label(stats["best"], lang),
        domains=num(stats["domains"], lang),
        relays=num(relays["verified"], lang),
        ports=" · ".join(num(p, lang) for p in stats["ports"]),
        updated=ago(stats["updated_at"], lang),
        state=t(lang, "admin.on" if stats["scanning"] else "admin.off"),
        pilot=t(lang, "admin.on" if pilot["enabled"] else "admin.off"),
        colos=colos,
    )
    return text, keyboards.simple_back(lang)


async def panel_overview(tg_id: int, lang: str) -> tuple[str, object]:
    panel = await db.get_panel(tg_id)
    if panel is None:
        return t(lang, "panel_none"), keyboards.simple_back(lang)

    endpoints = panel["endpoints"]
    best: Optional[float] = min((e.get("latency") or 0 for e in endpoints), default=None) or None
    text = t(
        lang,
        "panel_overview",
        host=esc(panel["host"]),
        uuid=esc(panel["uuid"]),
        count=num(len(endpoints), lang),
        best=ping_label(best, lang),
        health=t(lang, "panel_health_ok" if panel.get("healthy") else "panel_health_bad"),
        synced=ago(panel.get("synced_at"), lang),
        syncs=num(panel.get("syncs") or 0, lang),
        rebuilds=num(panel["rebuilds"], lang),
        updated=ago(panel["updated_at"], lang),
    )
    return text, keyboards.panel_menu(lang)


def operator_screen(lang: str, current: Optional[str]) -> tuple[str, object]:
    label = operators.label(current, lang) or t(lang, "operator_unset")
    return t(lang, "operator_menu", current=esc(label)), keyboards.operator_menu(lang)
