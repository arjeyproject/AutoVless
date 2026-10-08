#!/usr/bin/env python3
"""Redeploy stored AutoVless panels through the current Worker source.

Run inside the application container. It never prints Cloudflare tokens,
subscription tokens, private keys, or full UUIDs. A panel is saved only after
its Worker health check and endpoint WebSocket acceptance succeed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import db, deploy  # noqa: E402


def short(value: object) -> str:
    text = str(value or "")
    return text[:8] + "..." + text[-8:] if len(text) > 16 else "<set>"


async def main() -> int:
    await db.init()
    try:
        ids = await db.all_user_ids(include_banned=True)
        panels = []
        for tg_id in ids:
            panel = await db.get_panel(tg_id)
            if panel and panel.get("token"):
                panels.append((tg_id, panel))
        print(f"stored refreshable panels: {len(panels)}")
        failed = 0
        for tg_id, old in panels:
            host = str(old.get("host") or "")
            try:
                fresh = await deploy.refresh(old, force_scan=True)
                if not fresh.healthy or not fresh.endpoints:
                    failed += 1
                    print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason=health_gate")
                    continue
                await db.mark_panel_synced(tg_id, fresh.endpoints, fresh.relays, healthy=True)
                print(f"PASS host={fresh.host} uuid={short(fresh.uuid)} endpoints={len(fresh.endpoints)}")
            except Exception as exc:  # keep repairing the remaining panels
                failed += 1
                print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason={type(exc).__name__}")
        print(f"repair complete: failed={failed} passed={len(panels) - failed}")
        return 1 if failed else 0
    finally:
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
