#!/usr/bin/env python3
"""Apply verified clean-IP and WARP-pool wiring to an existing checkout.

This is an idempotent migration helper because the connected GitHub writer is
intentionally file-oriented. It changes only admin scan actions and the Mini App
WARP endpoint source; protocol generators remain the existing source of truth.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "bot" / "handlers" / "admin.py"
API = ROOT / "bot" / "api.py"

admin = ADMIN.read_text(encoding="utf-8")
if "adm:scan:ip" not in admin:
    admin = admin.replace(
        "from ..scanner import scanner\n",
        "from ..scanner import scanner\nfrom ..warppool import warp_pool\nfrom .. import warpstore\n",
        1,
    )
    old_keyboard = '''def engine_keyboard(lang: str) -> InlineKeyboardMarkup:\n    """Engine controls: sweep, apply, curate, warp."""\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [InlineKeyboardButton(text=t(lang, "btn.scan_now"), callback_data="adm:scan")],\n            [InlineKeyboardButton(text=t(lang, "btn.sync_now"), callback_data="adm:sync")],\n            [InlineKeyboardButton(text=t(lang, "btn.curate"), callback_data="adm:curate")],\n            [InlineKeyboardButton(text=t(lang, "btn.warp_rescan"), callback_data="wg:rescan")],\n            keyboards.back_row(lang, "adm:menu"),\n        ]\n    )\n'''
    new_keyboard = '''def engine_keyboard(lang: str) -> InlineKeyboardMarkup:\n    """Two explicit admin scans. Both use the real persisted health engines."""\n    ip_label = "🧼 اسکن آی‌پی تمیز" if lang == "fa" else "🧼 Scan clean IPs"\n    endpoint_label = "🧼 اسکن اندپوینت تمیز" if lang == "fa" else "🧼 Scan clean endpoints"\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [\n                InlineKeyboardButton(text=ip_label, callback_data="adm:scan:ip"),\n                InlineKeyboardButton(text=endpoint_label, callback_data="adm:scan:endpoint"),\n            ],\n            [InlineKeyboardButton(text=t(lang, "btn.sync_now"), callback_data="adm:sync")],\n            [InlineKeyboardButton(text=t(lang, "btn.curate"), callback_data="adm:curate")],\n            keyboards.back_row(lang, "adm:menu"),\n        ]\n    )\n'''
    if old_keyboard not in admin:
        raise SystemExit("admin engine keyboard block not found")
    admin = admin.replace(old_keyboard, new_keyboard, 1)

    old_scan = '''    elif action == "scan":\n        await call.answer(t(lang, "scan_started"))\n        await scanner.scan_once(batch=max(320, settings.scan_batch // 2))\n        await show_engine(call, lang)\n        return\n'''
    new_scan = '''    elif action == "scan:ip":\n        await call.answer(t(lang, "scan_started"))\n        await scanner.scan_once(batch=max(320, settings.scan_batch // 2))\n        panel_rows = await db.fetch_all("SELECT tg_id FROM panels WHERE token_enc IS NOT NULL")\n        await db.queue_panel_refresh([int(row["tg_id"]) for row in panel_rows])\n        synced = await autopilot.cycle(limit=len(panel_rows)) if panel_rows else 0\n        rows = await db.fetch_all(\n            "SELECT ip, port, latency, jitter, score, colo FROM clean_ips "\n            "WHERE verified = 1 AND fails < ? ORDER BY score ASC, latency ASC LIMIT 60",\n            (settings.max_fails,),\n        )\n        listing = "\\n".join(\n            f"✅ <code>{esc(row['ip'])}:{row['port']}</code> · "\n            f"{ping_label(row['latency'], lang)} · score {float(row['score'] or 0):.1f}"\n            for row in rows\n        ) or "-"\n        title = "🧼 <b>آی‌پی‌های تمیز تأییدشده</b>" if lang == "fa" else "🧼 <b>Verified clean IPs</b>"\n        await call.message.answer(title + f"\\nconfigs refreshed: {synced}\\n" + listing)\n        await show_engine(call, lang)\n        return\n    elif action == "scan:endpoint":\n        await call.answer(t(lang, "scan_started"))\n        reports = await warp_pool.refresh_all(force=True)\n        rows = await warpstore.best(60, stable_only=True)\n        listing = "\\n".join(\n            f"✅ <code>{esc(str(row['ip']))}:{row['port']}</code> · "\n            f"{ping_label(row['latency'], lang)} · health {row['health']}"\n            for row in rows\n        ) or "-"\n        title = "🧼 <b>اندپوینت‌های تمیز تأییدشده</b>" if lang == "fa" else "🧼 <b>Verified clean endpoints</b>"\n        summary = ", ".join(f"{r.family}:{r.status}/{r.stored}" for r in reports)\n        await call.message.answer(title + f"\\n{summary}\\n" + listing)\n        await show_engine(call, lang)\n        return\n'''
    if old_scan not in admin:
        raise SystemExit("admin scan branch not found")
    admin = admin.replace(old_scan, new_scan, 1)
    ADMIN.write_text(admin, encoding="utf-8")

api = API.read_text(encoding="utf-8")
if "from .warppool import warp_pool" not in api:
    api = api.replace(
        "from .warpconf import",
        "from .warppool import warp_pool\nfrom .warpconf import",
        1,
    ) if "from .warpconf import" in api else api.replace(
        "from . import (",
        "from .warppool import warp_pool\nfrom . import (",
        1,
    )
old_warp = '''async def _warp_endpoints(family: str) -> list[dict]:\n    endpoints = await db.best_warp_endpoints(12, stable_only=True)\n    if not endpoints:\n        endpoints = await db.best_warp_endpoints(12, stable_only=False)\n    rows = [dict(item) for item in endpoints]\n    if family == "v6":\n        return [item for item in rows if ":" in str(item["ip"])] or rows\n    return [item for item in rows if ":" not in str(item["ip"])] or rows\n'''
new_warp = '''async def _warp_endpoints(family: str) -> list[dict]:\n    """Use only the real, health-scored WARP pool for Mini App configs."""\n    return [dict(item) for item in await warp_pool.pick(family, 12)]\n'''
if old_warp in api:
    api = api.replace(old_warp, new_warp, 1)
API.write_text(api, encoding="utf-8")
print("patched admin scan actions and Mini App WARP pool source")
