#!/usr/bin/env python3
"""Redeploy stored panels before probing them.

A stale Worker can fail before fetch() with Cloudflare 1101. Probing it before
uploading the current artifact can never repair it, so this utility first
uploads the current source and bindings, then lets deploy.refresh apply the
normal health and WebSocket/VLESS gates.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import aipin, db, deploy  # noqa: E402
from bot.cloudflare import CloudflareClient, CloudflareError  # noqa: E402


def short(value: object) -> str:
    text = str(value or "")
    return text[:8] + "..." + text[-8:] if len(text) > 16 else "<set>"


async def bootstrap(old: dict) -> None:
    """Upload current code before refresh probes the existing hostname."""
    token = str(old.get("token") or "")
    account_id = str(old["account_id"])
    script = str(old["script_name"])
    uuid = str(old["uuid"])
    host = str(old["host"])
    code = deploy._read_worker()
    endpoints = await deploy._select_endpoints(force_scan=True)
    relays = await deploy._select_relays()
    ai_relays, _ = await aipin.choose(relays, uuid)
    async with CloudflareClient(token) as cf:
        await cf.upload_script(account_id, script, code, deploy._bindings(uuid, host, endpoints, relays, ai_relays))
        await cf.enable_workers_dev(account_id, script)


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
                await bootstrap(old)
                fresh = await deploy.refresh(old, force_scan=True)
                if not fresh.healthy or not fresh.endpoints:
                    failed += 1
                    print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason=health_gate")
                    continue
                await db.mark_panel_synced(tg_id, fresh.endpoints, fresh.relays, healthy=True)
                print(f"PASS host={fresh.host} uuid={short(fresh.uuid)} endpoints={len(fresh.endpoints)}")
            except (CloudflareError, deploy.DeployError) as exc:
                failed += 1
                print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason={type(exc).__name__}")
            except Exception as exc:
                failed += 1
                print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason={type(exc).__name__}")
        print(f"repair complete: failed={failed} passed={len(panels) - failed}")
        return 1 if failed else 0
    finally:
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
