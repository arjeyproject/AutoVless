"""Autopilot: keeps every live panel pointed at healthy entry addresses.

A clean IP is a perishable thing. The scanner finding a better address is only
half the job; somebody has to put it in front of the configs people already
hold. Doing that by hand means telling users to press rebuild, which most never
do, so their configs quietly rot while the pool underneath is full of good
addresses.

This job closes that loop. Every cycle it takes the panels whose addresses have
gone stale, or that failed their last health check, and re-uploads their worker
with the current best endpoints. The script name and the panel uuid never
change, so the subscription link the user already has starts serving the new
addresses on its next refresh. Nothing is asked of the user.

It is deliberately slow and small: a handful of panels per cycle, one at a time,
with a pause between them, because the same box also runs the scanners.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from . import db, deploy
from .config import settings

log = logging.getLogger("autovless.autopilot")

GAP_SECONDS = 4.0


class Autopilot:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self.running: bool = False
        self.last_run: int = 0
        self.last_synced: int = 0
        self.last_failed: int = 0
        self.total_synced: int = 0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.autopilot:
            log.info("autopilot disabled by configuration")
            return
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="autopilot")
            log.info(
                "autopilot started (interval=%ss batch=%s max_age=%ss)",
                settings.autopilot_interval,
                settings.autopilot_batch,
                settings.autopilot_max_age,
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        # Give the scanners a head start so the first cycle has something better
        # to offer than what the panels already carry.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=90)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("autopilot cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.autopilot_interval)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------ #
    # work
    # ------------------------------------------------------------------ #

    async def cycle(self, limit: Optional[int] = None) -> int:
        """Refresh one batch of stale panels. Returns how many were updated."""
        if self._lock.locked():
            return 0
        if not await db.get_flag("autopilot"):
            return 0

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            synced = failed = 0
            try:
                batch = limit or settings.autopilot_batch
                due = await db.panels_due(batch, settings.autopilot_max_age)
                if not due:
                    self.last_run = db.now()
                    return 0

                for panel in due:
                    if self._stop.is_set():
                        break
                    ok = await self._sync(panel)
                    if ok:
                        synced += 1
                    else:
                        failed += 1
                    await asyncio.sleep(GAP_SECONDS)

                self.last_run = db.now()
                self.last_synced = synced
                self.last_failed = failed
                self.total_synced += synced
                await db.log_event(
                    "autopilot",
                    detail=(
                        f"synced={synced} failed={failed} "
                        f"elapsed={time.perf_counter() - started:.1f}s"
                    ),
                )
                log.info("autopilot: %s panels refreshed, %s failed", synced, failed)
                return synced
            finally:
                self.running = False

    async def _sync(self, panel: dict) -> bool:
        tg_id = int(panel["tg_id"])
        try:
            result = await deploy.refresh(panel)
        except deploy.DeployError as error:
            # A revoked token or a deleted worker is not worth retrying every
            # cycle. Stamp the sync time so the panel drops to the back of the
            # queue instead of blocking everyone behind it.
            log.info("autopilot skipped %s: %s", tg_id, error.reason)
            await db.mark_panel_synced(tg_id, panel.get("endpoints") or [], panel.get("relays") or [], False)
            await db.log_event("autopilot_skip", tg_id, error.reason)
            return False
        except Exception as error:  # noqa: BLE001
            log.warning("autopilot error on %s: %s", tg_id, error)
            return False

        await db.mark_panel_synced(tg_id, result.endpoints, result.relays, result.healthy)
        return True

    async def refresh_panel(self, tg_id: int, force_scan: bool = False) -> Optional[dict]:
        """On-demand refresh for a single panel, used by the panel screen."""
        panel = await db.get_panel(tg_id)
        if panel is None or not panel.get("token"):
            return None
        result = await deploy.refresh(panel, force_scan=force_scan)
        await db.mark_panel_synced(tg_id, result.endpoints, result.relays, result.healthy)
        return {
            "endpoints": result.endpoints,
            "relays": result.relays,
            "healthy": result.healthy,
            "host": result.host,
            "uuid": result.uuid,
        }

    async def stats(self) -> dict:
        return {
            "enabled": settings.autopilot and await db.get_flag("autopilot"),
            "running": self.running,
            "last_run": self.last_run,
            "last_synced": self.last_synced,
            "last_failed": self.last_failed,
            "total_synced": self.total_synced,
            "due": await db.due_count(settings.autopilot_max_age),
            "interval": settings.autopilot_interval,
            "batch": settings.autopilot_batch,
            "max_age": settings.autopilot_max_age,
        }


autopilot = Autopilot()
