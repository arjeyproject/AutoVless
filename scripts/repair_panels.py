#!/usr/bin/env python3
"""Repair stale panels without rescanning the whole Cloudflare address space.

The current panel endpoints are used for the first redeploy. Only after the
current Worker is live and the real client-path gate fails do we fall back to a
normal refresh/scan. This keeps repair bounded and prevents Ctrl-C from leaving
an in-flight scan looking like a failed deployment.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import aipin, db, deploy  # noqa: E402
from bot.cloudflare import CloudflareClient, CloudflareError  # noqa: E402


def short(value: object) -> str:
    text = str(value or "")
    return text[:8] + "..." + text[-8:] if len(text) > 16 else "<set>"


async def bootstrap(old: dict) -> None:
    """Upload the current artifact using the panel's existing endpoint set."""
    token = str(old.get("token") or "")
    uuid = str(old["uuid"])
    endpoints = list(old.get("endpoints") or [])
    if not endpoints:
        raise deploy.DeployError("panel has no stored endpoints")
    relays = list(old.get("relays") or [])
    ai_relays, _ = await aipin.choose(relays, uuid) if relays else ([], "")
    async with CloudflareClient(token) as cf:
        await cf.upload_script(
            str(old["account_id"]),
            str(old["script_name"]),
            deploy._read_worker(),
            deploy._bindings(uuid, str(old["host"]), endpoints, relays, ai_relays),
        )
        await cf.enable_workers_dev(str(old["account_id"]), str(old["script_name"]))


async def repair_one(tg_id: int, old: dict) -> bool:
    await bootstrap(old)
    host = str(old["host"])
    healthy, report = await deploy._health(host, str(old["uuid"]), attempts=3)
    if report:
        await deploy._demote_dead_relays(report)
    if healthy:
        accepted, rejected = await deploy._accept(host, list(old["endpoints"]))
        if accepted and not rejected:
            await db.mark_panel_synced(tg_id, accepted, old.get("relays") or [], healthy=True)
            return True
    # The artifact is now current. Only this fallback may scan for replacements.
    fresh = await deploy.refresh(old, force_scan=False)
    if not fresh.healthy or not fresh.endpoints:
        return False
    await db.mark_panel_synced(tg_id, fresh.endpoints, fresh.relays, healthy=True)
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
            host = str(old.get("host") or "")
            try:
                if await repair_one(tg_id, old):
                    print(f"PASS host={host} uuid={short(old.get('uuid'))}")
                else:
                    failed += 1
                    print(f"FAIL host={host} uuid={short(old.get('uuid'))} reason=health_gate")
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
