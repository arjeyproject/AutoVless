"""WARP endpoint engine: find clean endpoints, keep them clean, never block.

Cloudflare answers WARP on thousands of addresses across dozens of UDP ports and
every one of them behaves differently from a given network. Iranian DPI makes it
worse: an endpoint can complete a handshake and be torn down a second later,
which is indistinguishable from a healthy one if you only probe once.

Four moving parts:

  1. port discovery  which of the 50+ WARP UDP ports leave this box at all
  2. sweep           one real handshake against sampled addresses on those ports
  3. verify          several spaced handshakes per survivor, measuring latency,
                     jitter and loss, then scoring the three together
  4. watchdog        a small constant re-check of the endpoints already in use,
                     so a filtered address is retired within a couple of minutes
                     instead of at the next full sweep

One rule runs through all of it: nothing a user waits on may ever wait on a
scan. A sweep already in flight is *joined* rather than refused, every outcome
comes back as a distinct report instead of a bare zero, and if the pool is empty
a scan is kicked off in the background while the caller immediately gets the
long-lived defaults. That is what the old ``scan_once() -> 0`` could not express:
busy, empty and broken all rendered as the same "a scan is already running"
message.

The engine keeps its own throwaway WARP identity so nobody's personal account is
burned on probing.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import random
import statistics
import time
from dataclasses import dataclass, replace
from typing import Optional

from . import db, warp, warpstore, wireguard
from .config import settings
from .warptune import TUNE

log = logging.getLogger("autovless.warpscan")

IDENTITY_OPTION = "warp_scanner_identity"

# Cloudflare WARP endpoint pools.
PREFIXES_V4: tuple[str, ...] = (
    "162.159.192.0/24",
    "162.159.195.0/24",
    "188.114.96.0/24",
    "188.114.97.0/24",
    "188.114.98.0/24",
    "188.114.99.0/24",
)
PREFIXES_V6: tuple[str, ...] = (
    "2606:4700:d0::/64",
    "2606:4700:d1::/64",
)

# Ports WARP listens on. The first few are the ones that usually survive.
COMMON_PORTS: tuple[int, ...] = (2408, 500, 1701, 4500, 854, 894, 880, 943)
ALL_PORTS: tuple[int, ...] = (
    500, 854, 859, 864, 878, 880, 890, 891, 894, 903, 908, 928, 934, 939, 942,
    943, 945, 946, 955, 968, 987, 988, 1002, 1010, 1014, 1018, 1070, 1074,
    1180, 1387, 1701, 1843, 2371, 2408, 2506, 3138, 3476, 3581, 3854, 4177,
    4198, 4233, 4500, 5279, 5956, 7103, 7152, 7156, 7281, 7559, 8319, 8742,
    8854, 8886,
)

_NETWORKS_V4 = [ipaddress.ip_network(prefix) for prefix in PREFIXES_V4]


def sample_addresses(per_prefix: int) -> list[str]:
    """Random addresses spread evenly over the WARP pools."""
    picked: list[str] = []
    for network in _NETWORKS_V4:
        size = network.num_addresses
        offsets = random.sample(range(1, size - 1), min(max(1, per_prefix), size - 2))
        picked.extend(str(network.network_address + offset) for offset in offsets)
    random.shuffle(picked)
    return picked


def _subnet_of(ip: str) -> str:
    """Group key used to spread a user's endpoints over different subnets."""
    text = str(ip)
    return text.rsplit(".", 1)[0] if "." in text else text.rsplit(":", 1)[0]


@dataclass
class ScanReport:
    """What happened on a sweep, in a shape a handler can render directly.

    ``status`` is the whole point of this class:

      done      the sweep ran here and now
      joined    a sweep was already in flight and we waited for its result
      cooldown  too soon since the last one; ``wait`` says how many seconds
      failed    something broke; ``reason`` is safe to show
      disabled  the feature is switched off
    """

    status: str = "done"
    found: int = 0
    alive: int = 0
    best: Optional[float] = None
    ports: tuple[int, ...] = ()
    elapsed: float = 0.0
    wait: int = 0
    rescued: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"done", "joined"} and self.found > 0


class WarpScanner:
    def __init__(self) -> None:
        self._scan_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._side_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._inflight: Optional[asyncio.Future] = None
        self._stop = asyncio.Event()
        self._identity: Optional[dict] = None
        self._finished_at: float = 0.0
        self.ports: tuple[int, ...] = tuple(settings.warp_ports) or COMMON_PORTS
        self.running: bool = False
        self.last_run: int = 0
        self.last_found: int = 0
        self.last_report: Optional[ScanReport] = None

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.warp_enabled:
            log.info("warp engine disabled by configuration")
            return
        await warpstore.ensure_schema()
        self._stop.clear()
        if self._scan_task is None or self._scan_task.done():
            self._scan_task = asyncio.create_task(self._scan_loop(), name="warp-scanner")
            log.info("warp engine started (interval=%ss)", settings.warp_scan_interval)
        if TUNE.watch_enabled and (self._watch_task is None or self._watch_task.done()):
            self._watch_task = asyncio.create_task(self._watch_loop(), name="warp-watchdog")
            log.info("warp watchdog started (every %ss, top %s)", TUNE.watch_interval, TUNE.watch_size)

    async def stop(self) -> None:
        self._stop.set()
        for task in (self._scan_task, self._watch_task, *tuple(self._side_tasks)):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._scan_task = None
        self._watch_task = None
        self._side_tasks.clear()

    async def _sleep(self, seconds: float) -> bool:
        """Wait, unless we are shutting down. True means keep going."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(1.0, seconds))
        except asyncio.TimeoutError:
            return True
        return False

    async def _scan_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.scan(force=True)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("warp scan cycle failed")
            if not await self._sleep(settings.warp_scan_interval):
                return

    async def _watch_loop(self) -> None:
        """Keep the endpoints people are actually using honest.

        A full sweep every half hour is far too slow to notice that the address
        in someone's config was blackholed four minutes ago. This loop only
        re-checks the handful of endpoints at the top of the pool, which is cheap
        enough to run constantly, and demotes them the moment they go quiet.
        """
        if not await self._sleep(min(60, TUNE.watch_interval)):
            return
        while not self._stop.is_set():
            if not self._lock.locked():
                try:
                    await self.watch_once()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    log.exception("warp watchdog pass failed")
            if not await self._sleep(TUNE.watch_interval):
                return

    # ------------------------------------------------------------------ #
    # identity
    # ------------------------------------------------------------------ #

    async def identity(self) -> Optional[dict]:
        """A throwaway WARP device used purely for probing, cached in the db."""
        if self._identity:
            return self._identity

        stored = await db.get_option(IDENTITY_OPTION)
        if stored:
            try:
                candidate = json.loads(stored)
                if candidate.get("private_key") and candidate.get("peer_public_key"):
                    self._identity = candidate
                    return self._identity
            except (ValueError, AttributeError):
                log.info("stored scanner identity is unusable, registering a new one")

        try:
            fresh = await warp.provision()
        except warp.WarpError as error:
            log.warning("scanner identity could not be registered: %s", error)
            return None

        self._identity = fresh
        await db.set_option(IDENTITY_OPTION, json.dumps(fresh, ensure_ascii=False))
        log.info("scanner warp identity registered (%s)", fresh.get("account_type"))
        return fresh

    # ------------------------------------------------------------------ #
    # probing
    # ------------------------------------------------------------------ #

    async def _probe_once(
        self,
        host: str,
        port: int,
        identity: dict,
        semaphore: asyncio.Semaphore,
    ) -> Optional[float]:
        """One real handshake. Milliseconds, or None when nothing came back."""
        async with semaphore:
            try:
                return await wireguard.handshake_rtt(
                    host,
                    int(port),
                    identity["private_key"],
                    identity["peer_public_key"],
                    identity.get("reserved") or (0, 0, 0),
                    timeout=settings.warp_scan_timeout,
                )
            except (OSError, ValueError, asyncio.TimeoutError):
                return None

    async def _measure(
        self,
        host: str,
        port: int,
        identity: dict,
        semaphore: asyncio.Semaphore,
        probes: Optional[int] = None,
    ) -> Optional[dict]:
        """Latency, jitter and loss for one endpoint, from spaced handshakes.

        The old engine threw an endpoint away the moment one round failed, which
        on a busy uplink is how the pool ends up empty. Here a miss is data: it
        becomes a loss ratio, and the score decides whether the endpoint is good
        enough to hand out.
        """
        rounds = max(2, int(probes or TUNE.probes))
        samples: list[float] = []
        misses = 0

        for index in range(rounds):
            if index:
                await asyncio.sleep(TUNE.probe_gap)
            rtt = await self._probe_once(host, port, identity, semaphore)
            for _ in range(TUNE.probe_retries):
                if rtt is not None:
                    break
                await asyncio.sleep(0.25)
                rtt = await self._probe_once(host, port, identity, semaphore)
            if rtt is None:
                misses += 1
            else:
                samples.append(float(rtt))

        if not samples:
            return None

        latency = statistics.median(samples)
        jitter = (
            sum(abs(sample - latency) for sample in samples) / len(samples)
            if len(samples) > 1
            else 0.0
        )
        loss = misses / rounds
        return {
            "ip": host,
            "port": int(port),
            "latency": round(latency, 1),
            "jitter": round(jitter, 1),
            "loss": round(loss, 3),
            "score": warpstore.score_of(latency, jitter, loss),
            "stable": loss <= TUNE.loss_max,
        }

    async def discover_ports(self, identity: dict, semaphore: asyncio.Semaphore) -> list[int]:
        """Which WARP ports get out of this network. Cheap, and worth a lot."""
        if settings.warp_ports:
            return list(settings.warp_ports)

        probes = sample_addresses(1)[:4] or ["162.159.192.1"]
        probes = list(dict.fromkeys(probes + ["162.159.192.1"]))
        for wave in (COMMON_PORTS, tuple(p for p in ALL_PORTS if p not in COMMON_PORTS)):
            pairs = [(host, port) for port in wave for host in probes]
            results = await asyncio.gather(
                *(self._probe_once(host, port, identity, semaphore) for host, port in pairs),
                return_exceptions=True,
            )
            alive = {
                int(port)
                for (_, port), rtt in zip(pairs, results)
                if not isinstance(rtt, BaseException) and rtt is not None
            }
            if alive:
                ordered = sorted(
                    alive,
                    key=lambda port: COMMON_PORTS.index(port) if port in COMMON_PORTS else 99,
                )
                log.info("warp ports reachable: %s", ordered)
                return ordered[:6]
        log.warning("no warp port answered, falling back to the common list")
        return list(COMMON_PORTS[:3])

    async def _fast_pass(
        self,
        candidates: list[str],
        ports: list[int],
        identity: dict,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, dict]:
        """One handshake per address and port. Keeps the fastest port per address."""
        pairs = [(host, port) for host in candidates for port in ports]
        results = await asyncio.gather(
            *(self._probe_once(host, port, identity, semaphore) for host, port in pairs),
            return_exceptions=True,
        )
        best: dict[str, dict] = {}
        for (host, port), rtt in zip(pairs, results):
            if isinstance(rtt, BaseException) or rtt is None:
                continue
            current = best.get(host)
            if current is None or float(rtt) < current["latency"]:
                best[host] = {"ip": host, "port": int(port), "latency": float(rtt)}
        return best

    async def _verify_pass(self, shortlist: list[dict], identity: dict) -> list[dict]:
        """Second, spaced opinion on the survivors, with loss and jitter."""
        if not shortlist:
            return []
        semaphore = asyncio.Semaphore(max(4, min(24, settings.warp_scan_concurrency)))
        results = await asyncio.gather(
            *(
                self._measure(row["ip"], row["port"], identity, semaphore)
                for row in shortlist
            ),
            return_exceptions=True,
        )
        rows: list[dict] = []
        for item in results:
            if isinstance(item, BaseException) or item is None:
                continue
            rows.append(item)
        return rows

    async def _rescue(self, identity: dict) -> list[dict]:
        """Last resort: measure the long-lived defaults and keep whatever answers.

        An empty pool is worse than a mediocre one, because then every user gets
        the same hardcoded address with no measurement behind it.
        """
        semaphore = asyncio.Semaphore(8)
        results = await asyncio.gather(
            *(
                self._measure(host, port, identity, semaphore, probes=2)
                for host, port in warp.FALLBACK_ENDPOINTS
            ),
            return_exceptions=True,
        )
        rows: list[dict] = []
        for item in results:
            if isinstance(item, BaseException) or item is None:
                continue
            rows.append(dict(item, stable=False))
        return rows

    # ------------------------------------------------------------------ #
    # sweeps
    # ------------------------------------------------------------------ #

    async def scan(
        self,
        *,
        quick: bool = False,
        force: bool = False,
        sample: Optional[int] = None,
    ) -> ScanReport:
        """Run a sweep, or join the one already running. Never raises.

        This is the method the rescan button calls. It used to be possible for a
        user to press it, land on the background sweep's lock and be told to come
        back later while a perfectly good scan was running two lines away. Now
        they simply wait for that scan's result.
        """
        if not settings.warp_enabled:
            return ScanReport(status="disabled", reason="warp disabled")

        inflight = self._inflight
        if inflight is not None and not inflight.done():
            try:
                report = await asyncio.shield(inflight)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                return ScanReport(status="failed", reason=str(error)[:180])
            return replace(report, status="joined")

        gap = TUNE.quick_gap if quick else TUNE.full_gap
        waited = time.monotonic() - self._finished_at
        if not force and self._finished_at and waited < gap:
            return ScanReport(
                status="cooldown",
                wait=max(1, int(gap - waited)),
                found=self.last_found,
                ports=self.ports,
            )

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._inflight = future
        try:
            report = await self._sweep(quick=quick, sample=sample)
        except asyncio.CancelledError:
            if not future.done():
                future.cancel()
            self._inflight = None
            self._finished_at = time.monotonic()
            raise
        except Exception as error:  # noqa: BLE001
            log.exception("warp sweep crashed")
            report = ScanReport(status="failed", reason=str(error)[:180])
        self._finished_at = time.monotonic()
        self.last_report = report
        if not future.done():
            future.set_result(report)
        self._inflight = None
        return report

    async def _sweep(self, quick: bool = False, sample: Optional[int] = None) -> ScanReport:
        started = time.perf_counter()
        async with self._lock:
            self.running = True
            try:
                identity = await self.identity()
                if identity is None:
                    return ScanReport(status="failed", reason="warp identity unavailable")

                await warpstore.ensure_schema()
                semaphore = asyncio.Semaphore(settings.warp_scan_concurrency)

                ports = await self.discover_ports(identity, semaphore)
                self.ports = tuple(ports)

                per_prefix = sample or (
                    TUNE.quick_sample if quick else settings.warp_scan_sample
                )
                candidates = sample_addresses(per_prefix)
                answered = await self._fast_pass(candidates, list(ports[:3]), identity, semaphore)

                shortlist = sorted(answered.values(), key=lambda row: row["latency"])
                shortlist = shortlist[: settings.warp_verify_top]
                verified = await self._verify_pass(shortlist, identity)

                stable = [row for row in verified if row.get("stable")]
                rescued = False
                if not stable:
                    # Nothing survived. Keep the shaky rows if there are any, and
                    # fall back to the defaults so the pool is never empty.
                    stable = verified or await self._rescue(identity)
                    rescued = not verified and bool(stable)
                    if stable:
                        log.info("warp sweep found nothing stable, kept %s rows", len(stable))

                if stable:
                    await warpstore.upsert(stable)
                retired = await warpstore.retire()
                await warpstore.trim(settings.warp_pool_size)

                pool = await warpstore.stats()
                elapsed = time.perf_counter() - started
                self.last_run = db.now()
                self.last_found = int(pool["stable"]) or len(stable)

                await db.log_event(
                    "warp_scan",
                    detail=(
                        f"mode={'quick' if quick else 'full'} alive={len(answered)} "
                        f"verified={len(verified)} stored={len(stable)} "
                        f"pool={pool['stable']}/{pool['total']} retired={retired} "
                        f"ports={','.join(str(p) for p in ports[:3])} "
                        f"elapsed={elapsed:.1f}s"
                    ),
                )
                log.info(
                    "warp scan: %s answered, %s verified, %s stored, pool %s stable",
                    len(answered),
                    len(verified),
                    len(stable),
                    pool["stable"],
                )
                return ScanReport(
                    status="done",
                    found=self.last_found,
                    alive=len(answered),
                    best=pool.get("best"),
                    ports=self.ports,
                    elapsed=round(elapsed, 1),
                    rescued=rescued,
                )
            finally:
                self.running = False

    async def scan_once(self, sample: Optional[int] = None) -> int:
        """Compatibility entry point: how many stable endpoints the pool holds."""
        report = await self.scan(force=True, sample=sample)
        return report.found

    def request_scan(self, *, quick: bool = True, force: bool = False) -> None:
        """Kick off a sweep beside the caller. Fire and forget, by design."""
        task = asyncio.create_task(self._background_scan(quick=quick, force=force))
        self._side_tasks.add(task)
        task.add_done_callback(self._side_tasks.discard)

    async def _background_scan(self, quick: bool, force: bool) -> None:
        try:
            report = await self.scan(quick=quick, force=force)
            log.info(
                "background warp scan: status=%s stable=%s alive=%s",
                report.status,
                report.found,
                report.alive,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("background warp scan failed")

    # ------------------------------------------------------------------ #
    # watchdog
    # ------------------------------------------------------------------ #

    async def watch_once(self) -> int:
        """Re-check the endpoints in use. Returns how many were demoted."""
        rows = await warpstore.best(TUNE.watch_size, stable_only=False)
        if not rows:
            return 0
        identity = await self.identity()
        if identity is None:
            return 0

        semaphore = asyncio.Semaphore(min(8, max(2, TUNE.watch_size)))
        results = await asyncio.gather(
            *(
                self._measure(row["ip"], row["port"], identity, semaphore, probes=2)
                for row in rows
            ),
            return_exceptions=True,
        )

        dropped = 0
        for row, item in zip(rows, results):
            if isinstance(item, BaseException) or item is None:
                dropped += 1
                fails = await warpstore.mark_fail(row["ip"], row["port"])
                log.info(
                    "warp watchdog: %s:%s went quiet (%s strikes)",
                    row["ip"],
                    row["port"],
                    fails,
                )
                continue
            await warpstore.mark_ok(
                row["ip"], row["port"], item["latency"], item["jitter"], item["loss"]
            )

        if dropped:
            await db.log_event("warp_watch", detail=f"checked={len(rows)} dropped={dropped}")
            healthy = len(await warpstore.best(settings.warp_per_config, stable_only=True))
            if healthy < settings.warp_per_config:
                # The pool is thinning out. Refill it now rather than at the next
                # scheduled sweep, while nobody is waiting on it.
                self.request_scan(quick=True, force=True)
        return dropped

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def verify_one(self, host: str, port: int) -> Optional[float]:
        """Probe a single endpoint on demand, demoting it when it stays silent."""
        identity = await self.identity()
        if identity is None:
            return None
        semaphore = asyncio.Semaphore(2)
        result = await self._measure(host, port, identity, semaphore, probes=2)
        if result is None:
            await warpstore.mark_fail(host, port)
            return None
        await warpstore.mark_ok(host, port, result["latency"], result["jitter"], result["loss"])
        return float(result["latency"])

    def _fallback_rows(self, count: int) -> list[dict]:
        return [
            {
                "ip": host,
                "port": int(port),
                "latency": 0.0,
                "jitter": 0.0,
                "loss": 0.0,
                "score": 0.0,
                "stable": False,
            }
            for host, port in warp.FALLBACK_ENDPOINTS[: max(1, count)]
        ]

    async def _pool(self, count: int) -> list[dict]:
        rows = await warpstore.best(count * 6, stable_only=True, max_loss=TUNE.loss_max)
        if len(rows) < count:
            seen = {(row["ip"], row["port"]) for row in rows}
            rows += [
                row
                for row in await warpstore.best(count * 6, stable_only=False)
                if (row["ip"], row["port"]) not in seen
            ]
        return rows

    def _spread(self, rows: list[dict], count: int) -> list[dict]:
        """Spread the picks over subnets so one bad /24 cannot sink a user."""
        spread: list[dict] = []
        seen_subnets: set[str] = set()
        for row in rows:
            subnet = _subnet_of(row["ip"])
            if subnet in seen_subnets:
                continue
            seen_subnets.add(subnet)
            spread.append(row)
            if len(spread) >= count:
                break
        for row in rows:  # top up if the spread was too strict
            if len(spread) >= count:
                break
            if row not in spread:
                spread.append(row)
        return spread[:count]

    async def pick(self, count: Optional[int] = None) -> list[dict]:
        """Best endpoints for one config. Returns immediately, always.

        Config building is the one thing that must never stall, so this only ever
        reads the pool. If the pool has nothing yet, a scan is requested in the
        background and the caller gets the long-lived defaults right now.
        """
        count = int(count or settings.warp_per_config)
        rows = await self._pool(count)
        if not rows:
            self.request_scan(quick=True)
            return self._fallback_rows(count)
        return self._spread(rows, count)

    async def failover(
        self,
        endpoints: Optional[list[dict]] = None,
        count: Optional[int] = None,
    ) -> list[dict]:
        """Fresh endpoint list for a user, keeping a working one if it still works.

        Called when somebody presses refresh, and whenever their current address
        is suspect. A live endpoint stays at the front (their client keeps the
        session it already has) and only the spares behind it are replaced.
        """
        count = int(count or settings.warp_per_config)
        head = (endpoints or [None])[0]
        if head and head.get("ip"):
            latency = await self.verify_one(str(head["ip"]), int(head["port"]))
            if latency is not None:
                spares = [
                    row
                    for row in await self.pick(count + 1)
                    if str(row["ip"]) != str(head["ip"])
                ]
                return [dict(head, latency=latency)] + spares[: max(0, count - 1)]
            log.info("warp failover: %s:%s is gone, switching", head.get("ip"), head.get("port"))
        return await self.pick(count)

    def next_scan_in(self) -> int:
        if not self._finished_at:
            return 0
        return max(0, int(settings.warp_scan_interval - (time.monotonic() - self._finished_at)))

    async def stats(self) -> dict:
        data = await warpstore.stats()
        data["scanning"] = self.running
        data["last_run"] = self.last_run
        data["last_found"] = self.last_found
        data["ports"] = list(self.ports)
        data["watching"] = bool(
            TUNE.watch_enabled and self._watch_task is not None and not self._watch_task.done()
        )
        data["next_scan"] = self.next_scan_in()
        return data

    async def snapshot(self, limit: Optional[int] = None) -> list[dict]:
        return await warpstore.snapshot(limit)


warp_scanner = WarpScanner()
