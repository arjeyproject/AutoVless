#!/usr/bin/env python3
"""Replace stale/corrupted Workers with fresh deployments.

A broken script can keep returning Cloudflare 1101 even after an in-place upload.
This utility creates a new Worker script while preserving the panel UUID and
account, then persists the new host only after the real health gate.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import db, deploy  # noqa: E402
from bot.cloudflare import CloudflareError  # noqa: E402


def short(value: object) -> str:
    text = str(value or "")
    return text[:8] + "..." + text[-8:] if len(text) > 16 else "<set>"


async def repair_one(tg_id: int, old: dict) -> bool:
    reuse = {"account_id": str(old["account_id"]), "uuid": str(old["uuid"])}
    fresh = await deploy.build(str(old["token"]), reuse=reuse, force_scan=False)
    if not fresh.healthy or not fresh.endpoints:
        return False
    await db.save_panel(
        tg_id, fresh.account_id, fresh.script, fresh.host, fresh.uuid,
        str(old["token"]), fresh.endpoints, fresh.build_ms,
        relays=fresh.relays, healthy=True,
    )
    return True


async def main() -> int:
    await db.init()
    try:
        panels = []
        for tg_id in await db.all_user_ids(include_banned=True):
            panel = await db.get_panel(tg_id)
            if panel and panel.get("token"):
                panels.append((tg_id, panel))
        print(f"stored refreshable panels: {len(panels)}")
        failed = 0
        for tg_id, old in panels:
            old_host = str(old.get("host") or "")
            try:
                if await repair_one(tg_id, old):
                    print(f"PASS old_host={old_host} uuid={short(old.get('uuid'))}")
                else:
                    failed += 1
                    print(f"FAIL old_host={old_host} uuid={short(old.get('uuid'))} reason=health_gate")
            except (CloudflareError, deploy.DeployError) as exc:
                failed += 1
                print(f"FAIL old_host={old_host} uuid={short(old.get('uuid'))} reason={type(exc).__name__}")
            except Exception as exc:
                failed += 1
                print(f"FAIL old_host={old_host} uuid={short(old.get('uuid'))} reason={type(exc).__name__}")
        print(f"repair complete: failed={failed} passed={len(panels) - failed}")
        return 1 if failed else 0
    finally:
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
