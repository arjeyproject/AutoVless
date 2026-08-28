"""The curator: the agent that keeps the pool honest between sweeps.

The scanner's job is to find entry points. This one's job is to make sure the
pool never contains anything that has stopped working, because that is the half
that users actually feel. A clean IP is perishable: it is clean until an ISP
notices it, and the gap between "it stopped working" and "we stopped shipping
it" is exactly the window where somebody's config shows -1ms.

What used to happen: an address that went dark got its fails counter bumped and
stayed in the table. Selection filtered on ``fails < MAX_FAILS``, so it kept its
slot and kept getting handed out until three separate checks happened to catch
it, and nothing ever removed it. The pool grew, its average quality fell, and
panels drifted back to dead configs between sweeps.

What happens now, every cycle:

  1. take the addresses nobody has confirmed lately, oldest first, verified ones
     first because those are the rows users are holding right now
  2. re-run the client's own sentence against each: TLS with a live panel
     hostname as the SNI, then a WebSocket upgrade on the panel's path, and only
     a ``101`` counts
  3. record every pass and every miss, so each address carries a history rather
     than a single lucky measurement
  4. delete, not demote, anything that crossed the line: a run of consecutive
     misses, a long-run reliability under the floor, or nothing confirmed for
     hours
  5. ask the sweep to refill any port left under POOL_TARGET, so the pool grows
     back wider than the reap made it
  6. re-point every panel that was serving a reaped address, immediately

The safety valve in step 4 is the part worth reading twice. If nearly the whole
batch misses, the honest conclusion is not "the internet died": it is that this
box lost its route, or the reference panel we verify against was deleted. So
nothing is purged that cycle, the reference is dropped so the next sweep picks a
live one, and the passes are still recorded because good news is never dangerous.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from . import db, probe, proxies
from .autopilot import autopilot
from .config import settings
from .scanner import proxy_scanner, scanner
from .scanner_v2 import _score as clean_score
from .vless import WS_PATH, is_tls

log = logging.getLogger("autovless.curator")

# Let the scanners get a sweep in before the first reap, so the pool has
# something to be curated.
HEAD_START = 60.0
RELAY_TIMEOUT = 7.0


class Curator:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self.running = False
        self.last_run = 0
        self.last_checked = 0
        self.last_kept = 0
        self.last_dropped = 0
        self.last_pushed = 0
        self.last_grown = 0
        self.last_relays = 0
        self.total_dropped = 0
        self.total_pushed = 0
        self.aborted = 0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.curator:
            log.info("curator disabled by configuration")
            return
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="curator")
            log.info(
                "curator started (interval=%ss batch=%s strikes=%s floor=%.2f target=%s/port)",
                settings.curator_interval,
                settings.curator_batch,
                settings.curator_strikes,
                settings.curator_floor,
                settings.pool_target,
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
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=HEAD_START)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("curator cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.curator_interval)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------ #
    # work
    # ------------------------------------------------------------------ #

    async def cycle(self, limit: Optional[int] = None) -> dict:
        """One curation pass. Returns a small report, empty if it did not run."""
        if self._lock.locked():
            return {}
        if not await db.get_flag("curator"):
            return {}
        async with self._lock:
            self.running = True
            started = time.perf_counter()
            try:
                report = await self._work(limit)
            finally:
                self.running = False
                self.last_run = db.now()
            report["elapsed"] = round(time.perf_counter() - started, 1)
            return report

    async def _recheck(self, row: dict, reference: str, sem: asyncio.Semaphore):
        ip = str(row["ip"])
        port = int(row["port"])
        async with sem:
            result = await probe.measure(
                ip,
                port,
                tls=is_tls(port),
                host=reference or None,
                path=WS_PATH,
                rounds=settings.curator_rounds,
                required=settings.curator_required,
                timeout=settings.accept_timeout,
            )
        return row, result

    async def _work(self, limit: Optional[int]) -> dict:
        reference = await scanner.reference_host()
        rows = await db.due_for_recheck(limit or settings.curator_batch, settings.curator_recheck)

        # Deliberately gentler than the sweep: these probes are three rounds
        # each and the same box is running everything else.
        sem = asyncio.Semaphore(max(4, min(48, settings.scan_concurrency // 6)))
        outcome = await asyncio.gather(
            *(self._recheck(row, reference, sem) for row in rows)
        )

        passed = [(row, result) for row, result in outcome if result is not None]
        missed = [row for row, result in outcome if result is None]

        # Keep the good news first: recording a pass is never dangerous, and it
        # is what stops a healthy address from ageing into the stale purge.
        if passed:
            await db.store_clean_ips([
                {
                    "ip": str(row["ip"]),
                    "port": int(row["port"]),
                    "kind": str(row.get("kind") or "ip"),
                    "latency": result["latency"],
                    "jitter": result["jitter"],
                    "score": clean_score(
                        result["latency"], result["jitter"], str(row.get("kind") or "ip")
                    ),
                    "colo": result["colo"],
                    "verified": True,
                }
                for row, result in passed
            ])

        ratio = len(missed) / max(1, len(outcome))
        blind = bool(outcome) and ratio >= settings.curator_abort_ratio

        dead: list[tuple[str, int]] = []
        if blind:
            # Everything failed. That is a statement about us, not about them.
            self.aborted += 1
            log.warning(
                "curator refused to purge: %s of %s missed (%.0f%%), check=%s",
                len(missed), len(outcome), ratio * 100, "ws:" + reference if reference else "trace",
            )
            if reference and not settings.verify_host:
                # The panel we verify against is the most likely single cause,
                # so let the next sweep elect a live one.
                await db.set_option("verify_host", "")
            await db.log_event(
                "curator_abort", detail=f"checked={len(outcome)} missed={len(missed)}"
            )
        else:
            for row in missed:
                if await db.mark_ip_fail(str(row["ip"]), int(row["port"])):
                    dead.append((str(row["ip"]), int(row["port"])))
            dead.extend(await db.purge_negative())
            dead.extend(await db.purge_stale())
            dead = list(dict.fromkeys(dead))

        pushed = await self._push(dead)
        grown = await self._grow()
        relays = await self._relays()

        self.last_checked = len(outcome)
        self.last_kept = len(passed)
        self.last_dropped = len(dead)
        self.last_pushed = pushed
        self.last_grown = grown
        self.last_relays = relays
        self.total_dropped += len(dead)
        self.total_pushed += pushed

        health = await db.pool_health()
        await db.log_event(
            "curator",
            detail=(
                f"checked={len(outcome)} kept={len(passed)} dropped={len(dead)} "
                f"pushed={pushed} grown={grown} relays_dropped={relays} "
                f"fresh={health['fresh']} thin={len(health['thin'])}"
                + (" ABORTED" if blind else "")
            ),
        )
        log.info(
            "curator: checked %s, kept %s, deleted %s, pushed %s panels, grew %s, dropped %s relays",
            len(outcome), len(passed), len(dead), pushed, grown, relays,
        )
        return {
            "checked": len(outcome),
            "kept": len(passed),
            "dropped": len(dead),
            "pushed": pushed,
            "grown": grown,
            "relays": relays,
            "aborted": blind,
        }

    async def _push(self, dead: list[tuple[str, int]]) -> int:
        """Get reaped addresses out of live configs now, not eventually.

        Without this the pool is clean and the panels are not, which from a
        user's side is the same thing as doing nothing at all.
        """
        if not dead or not settings.curator_push:
            return 0
        affected = await db.panels_serving(dead)
        if not affected:
            return 0
        await db.queue_panel_refresh(affected)
        # The autopilot owns the upload path, its own lock and its own pacing,
        # so the curator only ever asks it to go early.
        synced = await autopilot.cycle(limit=min(len(affected), settings.curator_push_batch))
        log.info("curator queued %s panels, autopilot refreshed %s now", len(affected), synced)
        return len(affected)

    async def _grow(self) -> int:
        """Refill whatever the reap left thin, plus a margin.

        POOL_TARGET is per port and is measured in *fresh verified* rows, so a
        port that is technically full of week-old entries still counts as thin
        and still gets swept.
        """
        health = await db.pool_health()
        thin = health["thin"]
        if not thin:
            return 0
        batch = min(settings.scan_batch, max(256, 320 * len(thin)))
        found = await scanner.scan_once(batch=batch, wait=False)
        if found:
            log.info("curator grew the pool by %s (thin ports: %s)", found, thin)
        return found

    async def _relays(self) -> int:
        """Same judgement for the relay chain.

        A panel with a dead chain reaches nothing that sits behind Cloudflare,
        which users report as "it connects but nothing loads". Relays that stop
        forwarding are deleted, and a thin pool triggers a relay sweep.
        """
        rows = await proxies.due_for_recheck(
            max(8, settings.curator_batch // 6), settings.curator_recheck
        )
        dropped = 0
        for row in rows:
            host = str(row["host"])
            port = int(row["port"])
            latency = await probe.connect_ms(host, port, 6)
            result = (
                await probe.trace(host, port, True, RELAY_TIMEOUT)
                if latency is not None
                else None
            )
            if result is None:
                if await proxies.record_fail(host, port):
                    dropped += 1
                continue
            await proxies.store([
                {
                    "host": host,
                    "port": port,
                    "latency": latency,
                    "colo": result["colo"],
                    "verified": True,
                }
            ])

        if await proxies.count() < max(4, settings.proxy_per_panel * 2):
            await proxy_scanner.scan_once(wait=False)
        return dropped

    # ------------------------------------------------------------------ #
    # reporting
    # ------------------------------------------------------------------ #

    async def stats(self) -> dict:
        health = await db.pool_health()
        relay = await proxies.stats()
        return {
            "enabled": settings.curator and await db.get_flag("curator"),
            "running": self.running,
            "last_run": self.last_run,
            "checked": self.last_checked,
            "kept": self.last_kept,
            "dropped": self.last_dropped,
            "pushed": self.last_pushed,
            "grown": self.last_grown,
            "relays_dropped": self.last_relays,
            "total_dropped": self.total_dropped,
            "total_pushed": self.total_pushed,
            "aborted": self.aborted,
            "interval": settings.curator_interval,
            "batch": settings.curator_batch,
            "strikes": settings.curator_strikes,
            "floor": settings.curator_floor,
            "target": health["target"],
            "total": health["total"],
            "verified": health["verified"],
            "fresh": health["fresh"],
            "thin": health["thin"],
            "relays": int(relay.get("verified") or 0),
        }


curator = Curator()
