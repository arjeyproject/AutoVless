"""Screen composition shared by several handlers."""

from __future__ import annotations

from typing import Optional

from . import db, keyboards, operators
from .config import settings
from .i18n import num, t
from .scanner import scanner
from .utils import ago, esc, ping_label


async def main_menu(name: str, lang: str, is_admin: bool) -> tuple[str, object]:
    stats = await scanner.stats()
    text = t(
        lang,
        "main_menu",
        brand=esc(settings.brand),
        name=esc(name or settings.brand),
        pool=num(stats["total"], lang),
        fast=num(stats["fast"], lang),
        best=ping_label(stats["best"], lang),
        healthy=num(stats["verified"], lang),
    )
    return text, keyboards.main_menu(lang, is_admin)


async def network_status(lang: str) -> tuple[str, object]:
    stats = await scanner.stats()
    rows = await db.fetch_all(
        "SELECT colo, COUNT(*) AS hits FROM clean_ips WHERE colo IS NOT NULL "
        "GROUP BY colo ORDER BY hits DESC LIMIT 6"
    )
    colos = " \u00b7 ".join(f"{esc(row['colo'])} ({num(row['hits'], lang)})" for row in rows) or "-"
    state_key = "admin.on" if stats["scanning"] else "admin.off"
    text = t(
        lang,
        "network_status",
        total=num(stats["total"], lang),
        verified=num(stats["verified"], lang),
        fast=num(stats["fast"], lang),
        best=ping_label(stats["best"], lang),
        ports=" \u00b7 ".join(num(p, lang) for p in stats["ports"]),
        updated=ago(stats["updated_at"], lang),
        state=t(lang, state_key),
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
        rebuilds=num(panel["rebuilds"], lang),
        updated=ago(panel["updated_at"], lang),
    )
    return text, keyboards.panel_menu(lang)


def operator_screen(lang: str, current: Optional[str]) -> tuple[str, object]:
    label = operators.label(current, lang) or t(lang, "operator_unset")
    return t(lang, "operator_menu", current=esc(label)), keyboards.operator_menu(lang)
