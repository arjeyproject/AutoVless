"""Keeps live panels standing on fresh clean IPs.

A panel is only as good as the entry points baked into it. The scanners find
better addresses every few minutes, but nothing used to carry them across: a
panel kept the IPs it was born with until its owner noticed the configs had
gone slow and pressed Rebuild by hand.

This job closes that loop. For every panel we still hold a token for, it
compares the endpoints in use against the current pool and, when the pool is
genuinely better or the panel's own entries have gone stale, re-uploads the
same script under the same host and uuid with fresh endpoints.

Same host, same uuid, same subscription URL, so there is nothing for the user
to re-import: the worker serves its own subscription and clients pick the new
addresses up on their next refresh.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from . import db, deploy, vless
from .config import settings
from .scanner import scanner

log = logging.getLogger("autovless.refresher")


def _key(endpoint: dict) -> str:
    return f"{endpoint.get('ip')}:{int(endpoint.get('port') or 0)}"


def _mean_latency(endpoints: list[dict]) -> Optional[float]:
    values = [float(e.get("latency") or 0) for e in endpoints if e.get("latency")]
    if not values:
        return None
    return sum(values) / len(values)


class PanelRefresher:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._bot = None
        self.running: bool = False
        self.last_run: int = 0
        self.last_refreshed: int = 0

    def attach(self, bot) -> None:
        """Optional: lets the job tell a user their panel just got faster."""
        self._bot = bot

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.refresh_enabled:
            log.info("panel refresher disabled")
            return
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="panel-refresher")
            log.info("panel refresher started (every %ss)", settings.refresh_interval)

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
        # Give the scanners a beat to fill the pool before judging anybody's panel.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=min(300, settings.refresh_interval))
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await self.refresh_all()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("refresh cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.refresh_interval)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------ #
    # work
    # ------------------------------------------------------------------ #

    async def refresh_all(self) -> int:
        """Walk every panel once, slowly. Returns how many were refreshed."""
        if self._lock.locked():
            return 0

        async with self._lock:
            self.running = True
            refreshed = 0
            try:
                rows = await db.fetch_all("SELECT tg_id FROM panels ORDER BY updated_at ASC")
                if not rows:
                    return 0

                fresh_keys = await scanner.fresh_keys()
                candidate = await vless.collect_endpoints(scanner)
                if not candidate:
                    log.info("pool has nothing to offer yet, skipping this refresh round")
                    return 0

                for row in rows:
                    if self._stop.is_set():
                        break
                    try:
                        if await self.refresh_panel(int(row["tg_id"]), candidate, fresh_keys):
                            refreshed += 1
                    except Exception:  # noqa: BLE001
                        log.warning("refresh failed for %s", row["tg_id"], exc_info=True)
                    # One panel at a time, with a pause. This talks to the
                    # Cloudflare API on somebody else's account.
                    await asyncio.sleep(settings.refresh_gap)

                self.last_run = db.now()
                self.last_refreshed = refreshed
                if refreshed:
                    await db.log_event("refresh_cycle", detail=f"panels={len(rows)} refreshed={refreshed}")
                log.info("refresh cycle: %s panels checked, %s updated", len(rows), refreshed)
                return refreshed
            finally:
                self.running = False

    def _worth_it(self, current: list[dict], candidate: list[dict], fresh_keys: set[str]) -> Optional[str]:
        """Why this panel should be rebuilt, or None to leave it alone.

        Rebuilding for a 3ms gain would mean hammering the Cloudflare API for
        nothing, so there has to be a real reason.
        """
        if not current:
            return "panel has no endpoints on record"

        dead = [e for e in current if _key(e) not in fresh_keys]
        if len(dead) >= max(1, len(current) // 2):
            return f"{len(dead)} of {len(current)} entry points no longer verify"

        if len(candidate) > len(current):
            return f"pool can serve {len(candidate)} endpoints, panel has {len(current)}"

        before, after = _mean_latency(current), _mean_latency(candidate)
        if before is not None and after is not None and (before - after) >= settings.refresh_min_gain:
            return f"pool is {round(before - after)}ms faster on average"

        new_ports = {int(e["port"]) for e in candidate}
        missing = new_ports - {int(e["port"]) for e in current}
        if missing:
            return f"panel is missing port {', '.join(str(p) for p in sorted(missing))}"

        return None

    async def refresh_panel(
        self,
        tg_id: int,
        candidate: Optional[list[dict]] = None,
        fresh_keys: Optional[set[str]] = None,
    ) -> bool:
        panel = await db.get_panel(tg_id)
        if panel is None:
            return False
        if not panel.get("token"):
            # STORE_TOKENS is off, or the token was never kept. Nothing we can
            # push without asking the user for it again.
            return False

        if candidate is None:
            candidate = await vless.collect_endpoints(scanner)
        if fresh_keys is None:
            fresh_keys = await scanner.fresh_keys()
        if not candidate:
            return False

        reason = self._worth_it(panel.get("endpoints") or [], candidate, fresh_keys)
        if reason is None:
            return False

        log.info("refreshing panel %s: %s", panel["host"], reason)
        built = await deploy.build(panel["token"], reuse=panel)
        await db.update_panel_endpoints(tg_id, built.endpoints, built.build_ms)
        await db.log_event(
            "refresh",
            tg_id,
            f"host={built.host} endpoints={len(built.endpoints)} healthy={built.healthy} why={reason}",
        )

        if settings.refresh_notify and self._bot is not None:
            await self._notify(tg_id, panel, built)
        return True

    async def _notify(self, tg_id: int, panel: dict, built) -> None:
        best = min((float(e.get("latency") or 0) for e in built.endpoints), default=0)
        try:
            from .i18n import t

            message = t(
                "fa",
                "refresh.done",
                host=built.host,
                count=len(built.endpoints),
                ping=round(best),
            )
        except Exception:  # noqa: BLE001
            message = (
                f"\U0001f501 <b>{settings.brand}</b>\n"
                f"\u067e\u0646\u0644 \u0634\u0645\u0627 \u0631\u0648\u06cc \u0622\u06cc\u200c\u067e\u06cc\u200c\u0647\u0627\u06cc \u062a\u0627\u0632\u0647 \u062a\u0646\u0632\u06cc\u0645 \u0634\u062f.\n"
                f"\U0001f4e1 {len(built.endpoints)} \u06a9\u0627\u0646\u0641\u06cc\u06af \u00b7 \u0628\u0647\u062a\u0631\u06cc\u0646 {round(best)}ms\n"
                "\u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9 \u0639\u0648\u0636 \u0646\u0634\u062f\u0647\u060c \u0641\u0642\u0637 \u062f\u0631 \u0628\u0631\u0646\u0627\u0645\u0647 \u0627\u0634\u062a\u0631\u0627\u06a9 \u0631\u0627 \u0628\u0631\u0648\u0632 \u06a9\u0646\u06cc\u062f."
            )
        try:
            await self._bot.send_message(tg_id, message)
        except Exception:  # noqa: BLE001
            log.debug("could not notify %s about the refresh", tg_id)

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def stats(self) -> dict:
        return {
            "enabled": settings.refresh_enabled,
            "running": self.running,
            "interval": settings.refresh_interval,
            "last_run": self.last_run,
            "last_refreshed": self.last_refreshed,
            "panels": int(await db.scalar("SELECT COUNT(*) FROM panels")),
        }


refresher = PanelRefresher()
