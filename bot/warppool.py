"""Two WARP pools, ten healthy endpoints each, and an agent that keeps them that way.

Why two pools
-------------
Irancell (MTN) shapes and drops IPv4 WARP hard, while its IPv6 path is usually
left alone. Every other Iranian operator is the other way round. One mixed pool
cannot serve both: a user pressing a button has to be handed an endpoint of the
right *family*, not a lucky draw. So there are two pools, one per family, held at
``TUNE.pool_target`` healthy endpoints each.

What "healthy" means here
-------------------------
Exactly three things, and nothing softer:

  1. it completed a real, cryptographically verified WireGuard handshake, several
     times, spaced out, so DPI that kills a session one second in is caught;
  2. its WarpEP health score (loss first, then latency, then jitter) cleared
     ``TUNE.health_floor``;
  3. where the ``warpep`` package is installed, it carried real ICMP through a
     real tunnel and gave it back decrypted.

Anything that fails one of those is never written, and anything already stored
that starts failing is deleted rather than demoted. ``warpstore.upsert`` enforces
the floor itself, so the guarantee does not depend on this module remembering to
apply it.

The agent
---------
``PoolAgent`` is the part that runs on its own. Every pass it re-probes every
stored endpoint, deletes the dead, re-sorts the survivors by ping and tops up any
pool that has fallen below target. That is the whole job: nobody should ever have
to press a button for the pools to be correct, and the buttons in the admin panel
exist so a human can see the agent's work rather than do it.

Nothing here is ever awaited by a user-facing path. Refreshes run as background
tasks and report back into the message that started them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import db, warpep, warpstore
from .config import settings
from .warpep import V4, V6
from .warpscan import warp_scanner
from .warptune import TUNE

log = logging.getLogger("autovless.warppool")

FAMILIES: tuple[str, str] = (V4, V6)


@dataclass
class RefreshReport:
    """What one pool refresh did. Rendered straight onto the admin screen."""

    family: str = V4
    status: str = "done"          # done | busy | cooldown | failed | disabled
    probed: int = 0               # candidate addresses swept
    answered: int = 0             # answered at least one handshake
    healthy: int = 0              # cleared the health floor
    proven: int = 0               # carried real traffic through the tunnel
    stored: int = 0               # written into the pool
    dropped: int = 0              # deleted from the pool during hygiene
    pool: int = 0                 # healthy rows in the pool afterwards
    target: int = 0
    best: Optional[float] = None
    ports: tuple[int, ...] = ()
    elapsed: float = 0.0
    wait: int = 0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "done" and self.pool > 0

    @property
    def full(self) -> bool:
        return self.pool >= self.target


@dataclass
class AuditReport:
    """The answer to "is our pool actually healthy right now?"."""

    status: str = "done"          # done | busy | failed | disabled
    checked: int = 0
    alive: int = 0
    dead: int = 0
    removed: int = 0
    elapsed: float = 0.0
    reason: str = ""
    families: dict = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        """True only when both pools are at target and nothing is failing."""
        if self.status != "done" or not self.families:
            return False
        return all(item["healthy"] >= item["target"] for item in self.families.values())

    @property
    def verdict(self) -> str:
        if self.status != "done":
            return self.status
        if self.healthy:
            return "healthy"
        if any(item["healthy"] for item in self.families.values()):
            return "degraded"
        return "empty"


class WarpPool:
    """Owns both family pools, the refresh, the audit and the agent loop."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {family: asyncio.Lock() for family in FAMILIES}
        self._audit_lock = asyncio.Lock()
        self._finished: dict[str, float] = {}
        self._jobs: set[asyncio.Task] = set()
        self._agent: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.ports: dict[str, tuple[int, ...]] = {family: () for family in FAMILIES}
        self.last_refresh: dict[str, Optional[RefreshReport]] = {f: None for f in FAMILIES}
        self.last_audit: Optional[AuditReport] = None
        self.passes: int = 0

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deep_wanted(deep: Optional[bool]) -> bool:
        if deep is None:
            return bool(TUNE.deep_verify and warpep.installed())
        return bool(deep and warpep.installed())

    def _spawn(self, coro, name: str) -> asyncio.Task:
        """Run something beside the caller and keep a reference to it."""
        task = asyncio.create_task(coro, name=name)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)
        return task

    async def _deep_pass(self, identity: dict, rows: list[dict], deep: bool) -> int:
        """Prove the best rows really carry traffic. Returns how many did.

        Only the top few get this: it opens a real tunnel and waits for ICMP, so
        it is expensive, and the rows below the cut are still handshake-verified.
        A row that answers and then swallows traffic is marked ``verified=False``,
        which ``warpstore`` treats as unfit for a pool.
        """
        if not deep or not rows:
            return 0
        proven = 0
        for row in rows[: max(0, int(TUNE.deep_top))]:
            outcome = await warpep.deep_verify(
                identity,
                row["ip"],
                row["port"],
                echoes=TUNE.deep_echoes,
                timeout=TUNE.deep_timeout,
            )
            if outcome is None:
                continue
            row["verified"] = outcome
            row["health"] = warpep.health(
                row["latency"], row.get("jitter") or 0.0, row.get("loss") or 0.0, verified=outcome
            )
            if outcome:
                proven += 1
            else:
                # It handshakes and carries nothing. Worse than dead, because it
                # looks alive to every cheap check there is.
                row["stable"] = False
                await warpstore.drop(row["ip"], row["port"])
        return proven

    async def _control_rescue(self, identity: dict, family: str) -> list[dict]:
        """Measure Cloudflare's own published endpoints for this family.

        Used only when a pool is empty. These are still measured for real and
        still have to clear the floor, so an empty pool is never papered over
        with an address nobody has tested.
        """
        rows: list[dict] = []
        for host, port in warpep.CONTROL.get(family, ()):
            measured = await warp_scanner.measure(host, port, probes=2)
            if measured is None:
                continue
            measured["stable"] = True
            rows.append(measured)
        return rows

    # ------------------------------------------------------------------ #
    # refresh
    # ------------------------------------------------------------------ #

    async def refresh(
        self,
        family: str,
        deep: Optional[bool] = None,
        force: bool = False,
    ) -> RefreshReport:
        """Sweep this family's address space and refill its pool. Never raises."""
        code = warpep.normalise_family(family)
        report = RefreshReport(family=code, target=int(TUNE.pool_target))

        if not settings.warp_enabled:
            return RefreshReport(family=code, status="disabled", reason="warp disabled")

        lock = self._locks[code]
        if lock.locked():
            counts = await warpstore.counts(code)
            return RefreshReport(
                family=code,
                status="busy",
                pool=counts["healthy"],
                target=counts["target"],
                best=counts["best"],
            )

        waited = time.monotonic() - self._finished.get(code, 0.0)
        if not force and self._finished.get(code) and waited < TUNE.refresh_gap:
            counts = await warpstore.counts(code)
            return RefreshReport(
                family=code,
                status="cooldown",
                wait=max(1, int(TUNE.refresh_gap - waited)),
                pool=counts["healthy"],
                target=counts["target"],
                best=counts["best"],
            )

        started = time.perf_counter()
        async with lock:
            try:
                report = await self._sweep(code, deep)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                log.exception("pool refresh for %s crashed", code)
                report = RefreshReport(
                    family=code,
                    status="failed",
                    target=int(TUNE.pool_target),
                    reason=str(error)[:180],
                )
            finally:
                self._finished[code] = time.monotonic()

        report.elapsed = round(time.perf_counter() - started, 1)
        self.last_refresh[code] = report
        return report

    async def _sweep(self, family: str, deep: Optional[bool]) -> RefreshReport:
        report = RefreshReport(family=family, target=int(TUNE.pool_target))
        identity = await warp_scanner.identity()
        if identity is None:
            report.status = "failed"
            report.reason = "warp identity unavailable"
            return report

        await warpstore.ensure_schema()
        want_deep = self._deep_wanted(deep)
        semaphore = asyncio.Semaphore(max(8, int(settings.warp_scan_concurrency)))

        ports = await warp_scanner.discover_ports_for(family, identity, semaphore)
        ports = list(ports)[: max(1, int(TUNE.pool_ports))]
        self.ports[family] = tuple(ports)
        report.ports = tuple(ports)

        addresses = warpep.candidates(family, TUNE.pool_sample)
        report.probed = len(addresses)
        answered = await warp_scanner.fast_pass(addresses, ports, identity, semaphore)
        report.answered = len(answered)

        # Only the fastest few are worth several spaced handshakes each.
        shortlist = sorted(answered.values(), key=lambda row: row["latency"])
        shortlist = shortlist[: max(TUNE.pool_target * 3, int(settings.warp_verify_top))]
        verified = await warp_scanner.verify_rows(shortlist, identity)

        healthy = [
            row
            for row in verified
            if row.get("stable")
            and warpep.health(row["latency"], row["jitter"], row["loss"]) >= TUNE.health_floor
        ]
        if not healthy:
            log.info("pool %s: nothing cleared the floor, measuring the control endpoints", family)
            healthy = [
                row
                for row in await self._control_rescue(identity, family)
                if warpep.health(row["latency"], row["jitter"], row["loss"]) >= TUNE.health_floor
            ]
        healthy.sort(key=lambda row: row["latency"])
        report.healthy = len(healthy)

        report.proven = await self._deep_pass(identity, healthy, want_deep)
        keepers = [row for row in healthy if row.get("verified") is not False]
        # Spread the winners over distinct blocks first so one blackholed /24
        # cannot become the entire pool.
        ordered = warpep.spread(keepers, TUNE.pool_target * 2) + keepers
        seen: set[tuple] = set()
        unique: list[dict] = []
        for row in ordered:
            key = (str(row["ip"]), int(row["port"]))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        report.stored = await warpstore.upsert(unique)
        report.dropped = await warpstore.retire()
        report.dropped += await warpstore.purge_unhealthy()
        report.dropped += await warpstore.trim(TUNE.pool_target, family=family)

        counts = await warpstore.counts(family)
        report.pool = counts["healthy"]
        report.best = counts["best"]
        report.status = "done"

        await db.log_event(
            "warp_pool",
            detail=(
                f"family={family} probed={report.probed} answered={report.answered} "
                f"healthy={report.healthy} proven={report.proven} stored={report.stored} "
                f"dropped={report.dropped} pool={report.pool}/{report.target} "
                f"ports={','.join(str(p) for p in ports)} deep={'on' if want_deep else 'off'}"
            ),
        )
        log.info(
            "pool %s refreshed: %s answered, %s healthy, %s stored, pool %s/%s",
            family,
            report.answered,
            report.healthy,
            report.stored,
            report.pool,
            report.target,
        )
        return report

    async def refresh_all(
        self,
        deep: Optional[bool] = None,
        force: bool = False,
    ) -> list[RefreshReport]:
        """Both families, one after the other so they do not fight for sockets."""
        return [await self.refresh(family, deep=deep, force=force) for family in FAMILIES]

    def request_refresh(self, family: Optional[str] = None, force: bool = True) -> None:
        """Fire and forget. What the admin button uses so it can answer instantly."""
        if family is None:
            self._spawn(self.refresh_all(force=force), "warp-pool-refresh-all")
            return
        code = warpep.normalise_family(family)
        self._spawn(self.refresh(code, force=force), f"warp-pool-refresh-{code}")

    # ------------------------------------------------------------------ #
    # audit
    # ------------------------------------------------------------------ #

    async def audit(self, deep: Optional[bool] = None) -> AuditReport:
        """Re-probe every stored endpoint, delete the dead, report the truth.

        This is the button that answers "is our pool healthy or not". It walks
        both pools, not a sample, because a partial answer to that question is
        worth nothing.
        """
        if not settings.warp_enabled:
            return AuditReport(status="disabled", reason="warp disabled")
        if self._audit_lock.locked():
            return AuditReport(status="busy")

        started = time.perf_counter()
        async with self._audit_lock:
            identity = await warp_scanner.identity()
            if identity is None:
                return AuditReport(status="failed", reason="warp identity unavailable")

            want_deep = self._deep_wanted(deep)
            report = AuditReport()

            for family in FAMILIES:
                rows = await warpstore.rows_of(family, limit=TUNE.pool_target * 4)
                alive: list[dict] = []
                dead = 0
                for row in rows:
                    measured = await warp_scanner.measure(
                        row["ip"], row["port"], probes=max(2, TUNE.probes - 1)
                    )
                    report.checked += 1
                    if measured is None:
                        dead += 1
                        await warpstore.drop(row["ip"], row["port"])
                        log.info(
                            "audit: %s is gone, removed from the %s pool",
                            warpep.host_port(row["ip"], row["port"]),
                            family,
                        )
                        continue
                    points = warpep.health(
                        measured["latency"], measured["jitter"], measured["loss"]
                    )
                    if points < TUNE.health_floor:
                        dead += 1
                        await warpstore.drop(row["ip"], row["port"])
                        continue
                    alive.append(measured)

                proven = await self._deep_pass(identity, alive, want_deep)
                keepers = [row for row in alive if row.get("verified") is not False]
                dead += len(alive) - len(keepers)
                for row in keepers:
                    await warpstore.mark_ok(
                        row["ip"],
                        row["port"],
                        row["latency"],
                        row["jitter"],
                        row["loss"],
                        verified=row.get("verified"),
                    )

                report.alive += len(keepers)
                report.dead += dead
                counts = await warpstore.counts(family)
                report.families[family] = {
                    "family": family,
                    "checked": len(rows),
                    "alive": len(keepers),
                    "proven": proven,
                    "dead": dead,
                    "healthy": counts["healthy"],
                    "target": counts["target"],
                    "best": counts["best"],
                    "avg": counts["avg"],
                    "full": counts["full"],
                }

            report.removed = await warpstore.purge_unhealthy()
            for family in FAMILIES:
                await warpstore.trim(TUNE.pool_target, family=family)
                # A pool that came out of the audit short refills itself now,
                # while nobody is waiting on it.
                if report.families.get(family, {}).get("healthy", 0) < TUNE.pool_target:
                    self.request_refresh(family, force=True)

            report.elapsed = round(time.perf_counter() - started, 1)
            report.status = "done"
            self.last_audit = report

        await db.log_event(
            "warp_audit",
            detail=(
                f"checked={report.checked} alive={report.alive} dead={report.dead} "
                f"removed={report.removed} verdict={report.verdict} "
                f"elapsed={report.elapsed}s"
            ),
        )
        return report

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def pick(self, family: str, count: Optional[int] = None) -> list[dict]:
        """Healthy endpoints of one family, best ping first.

        Returns immediately. If the pool is cold it measures Cloudflare's own
        published endpoints for that family on the spot rather than handing back
        an untested address, and kicks a refresh in the background. An empty list
        means the network genuinely has nothing for this family right now, and the
        caller should say so instead of shipping a config that cannot work.
        """
        code = warpep.normalise_family(family)
        wanted = max(1, int(count or settings.warp_per_config))
        rows = await warpstore.pool(code, limit=max(wanted, TUNE.pool_target))
        if rows:
            return warpep.spread(rows, wanted)

        self.request_refresh(code, force=True)
        identity = await warp_scanner.identity()
        if identity is None:
            return []
        rescue = [
            row
            for row in await self._control_rescue(identity, code)
            if warpep.health(row["latency"], row["jitter"], row["loss"]) >= TUNE.health_floor
        ]
        if rescue:
            rescue.sort(key=lambda row: row["latency"])
            await warpstore.upsert(rescue)
        return rescue[:wanted]

    async def status(self) -> dict:
        """Everything the admin pool screen prints."""
        families = {family: await warpstore.counts(family) for family in FAMILIES}
        return {
            "families": families,
            "target": int(TUNE.pool_target),
            "floor": int(TUNE.health_floor),
            "source": warpep.describe(),
            "deep": bool(TUNE.deep_verify and warpep.installed()),
            "deep_possible": warpep.installed(),
            "agent": bool(self._agent is not None and not self._agent.done()),
            "agent_interval": int(TUNE.agent_interval),
            "passes": self.passes,
            "busy": any(lock.locked() for lock in self._locks.values())
            or self._audit_lock.locked(),
            "ports": {family: list(self.ports.get(family, ())) for family in FAMILIES},
            "healthy": all(item["full"] for item in families.values()),
            "last_audit": self.last_audit,
        }

    # ------------------------------------------------------------------ #
    # the agent
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.warp_enabled:
            log.info("warp pools disabled by configuration")
            return
        await warpstore.ensure_schema()
        self._stop.clear()
        if not TUNE.agent_enabled:
            log.info("warp pool agent disabled by configuration")
            return
        if self._agent is None or self._agent.done():
            self._agent = asyncio.create_task(self._agent_loop(), name="warp-pool-agent")
            log.info(
                "warp pool agent started (every %ss, %s per family, floor %s, deep %s)",
                TUNE.agent_interval,
                TUNE.pool_target,
                TUNE.health_floor,
                "on" if (TUNE.deep_verify and warpep.installed()) else "off",
            )

    async def stop(self) -> None:
        self._stop.set()
        for task in (self._agent, *tuple(self._jobs)):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._agent = None
        self._jobs.clear()

    async def _sleep(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(1.0, seconds))
        except asyncio.TimeoutError:
            return True
        return False

    async def _agent_loop(self) -> None:
        """Audit, bury the dead, re-sort by ping, top up. Forever."""
        # A cold start gets its pools before it gets its first audit, otherwise
        # the first users of the day are told to come back later.
        for family in FAMILIES:
            counts = await warpstore.counts(family)
            if counts["healthy"] < TUNE.pool_target:
                await self.refresh(family, force=True)
        while not self._stop.is_set():
            if not await self._sleep(TUNE.agent_interval):
                return
            try:
                await self.pass_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("warp pool agent pass failed")

    async def pass_once(self) -> AuditReport:
        """One agent pass. Also what the admin audit button runs."""
        self.passes += 1
        report = AuditReport(status="done")
        if self.passes % max(1, int(TUNE.agent_audit_every)) == 0:
            report = await self.audit()
        for family in FAMILIES:
            counts = await warpstore.counts(family)
            if counts["healthy"] < TUNE.pool_target:
                await self.refresh(family, force=True)
        return report


warp_pool = WarpPool()
