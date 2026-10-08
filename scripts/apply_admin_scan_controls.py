#!/usr/bin/env python3
"""Apply the admin clean-IP/WARP endpoint scan controls to an existing checkout.

The patch is intentionally narrow: it preserves the current bot, menus, database,
scanner engines, and Mini App. It only replaces the admin engine scan controls and
adds real result lists after each completed scan.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "bot" / "handlers" / "admin.py"

text = TARGET.read_text(encoding="utf-8")
if "adm:scan:ip" in text and "adm:scan:endpoint" in text:
    print("admin scan controls already patched")
    raise SystemExit(0)

text = text.replace(
    "from ..scanner import scanner\n",
    "from ..scanner import scanner\nfrom ..warpscan import warp_scanner\nfrom .. import warpstore\n",
)

old_keyboard = '''def engine_keyboard(lang: str) -> InlineKeyboardMarkup:\n    """Engine controls: sweep, apply, curate, warp."""\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [InlineKeyboardButton(text=t(lang, "btn.scan_now"), callback_data="adm:scan")],\n            [InlineKeyboardButton(text=t(lang, "btn.sync_now"), callback_data="adm:sync")],\n            [InlineKeyboardButton(text=t(lang, "btn.curate"), callback_data="adm:curate")],\n            [InlineKeyboardButton(text=t(lang, "btn.warp_rescan"), callback_data="wg:rescan")],\n            keyboards.back_row(lang, "adm:menu"),\n        ]\n    )\n'''
new_keyboard = '''def engine_keyboard(lang: str) -> InlineKeyboardMarkup:\n    """Admin-only real scans. Results are posted after each scan completes."""\n    ip_label = "🧼 اسکن آی‌پی تمیز" if lang == "fa" else "🧼 Scan clean IPs"\n    endpoint_label = "🧼 اسکن اندپوینت تمیز" if lang == "fa" else "🧼 Scan clean endpoints"\n    return InlineKeyboardMarkup(\n        inline_keyboard=[\n            [\n                InlineKeyboardButton(text=ip_label, callback_data="adm:scan:ip"),\n                InlineKeyboardButton(text=endpoint_label, callback_data="adm:scan:endpoint"),\n            ],\n            [InlineKeyboardButton(text=t(lang, "btn.sync_now"), callback_data="adm:sync")],\n            [InlineKeyboardButton(text=t(lang, "btn.curate"), callback_data="adm:curate")],\n            keyboards.back_row(lang, "adm:menu"),\n        ]\n    )\n'''
if old_keyboard not in text:
    raise SystemExit("could not find engine_keyboard block")
text = text.replace(old_keyboard, new_keyboard)

old_scan = '''    elif action == "scan":\n        await call.answer(t(lang, "scan_started"))\n        await scanner.scan_once(batch=max(320, settings.scan_batch // 2))\n        await show_engine(call, lang)\n        return\n'''
new_scan = '''    elif action == "scan:ip":\n        await call.answer(t(lang, "scan_started"))\n        await scanner.scan_once(batch=max(320, settings.scan_batch // 2))\n        rows = await db.fetch_all(\n            "SELECT ip, port, latency, score, colo FROM clean_ips "\n            "WHERE verified = 1 ORDER BY score ASC, latency ASC LIMIT 60"\n        )\n        listing = "\\n".join(\n            f"✅ <code>{esc(row['ip'])}:{row['port']}</code> · "\n            f"{ping_label(row['latency'], lang)} · score {round(float(row['score'] or 0), 1)}"\n            for row in rows\n        ) or "-"\n        await call.message.answer(\n            ("🧼 <b>آی‌پی‌های تمیز تأییدشده</b>\\n" if lang == "fa" else "🧼 <b>Verified clean IPs</b>\\n") + listing\n        )\n        await show_engine(call, lang)\n        return\n    elif action == "scan:endpoint":\n        await call.answer(t(lang, "scan_started"))\n        report = await warp_scanner.scan(force=True)\n        rows = await warpstore.best(60, stable_only=True)\n        listing = "\\n".join(\n            f"✅ <code>{esc(str(row['ip']))}:{row['port']}</code> · "\n            f"{ping_label(row['latency'], lang)}"\n            for row in rows\n        ) or "-"\n        title = "🧼 <b>اندپوینت‌های تمیز تأییدشده</b>" if lang == "fa" else "🧼 <b>Verified clean endpoints</b>"\n        status = f"\\nstatus={report.status}, found={report.found}, alive={report.alive}"\n        await call.message.answer(title + status + "\\n" + listing)\n        await show_engine(call, lang)\n        return\n'''
if old_scan not in text:
    raise SystemExit("could not find old scan branch")
text = text.replace(old_scan, new_scan)

TARGET.write_text(text, encoding="utf-8")
print(f"patched {TARGET}")
