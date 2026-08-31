"""WARP endpoint engine: find clean endpoints, keep them clean, never block.

Cloudflare answers WARP on thousands of addresses across dozens of UDP ports and
every one of them behaves differently from a given network. Iranian DPI makes it
worse: an endpoint can complete a handshake and be torn down a second later,
which is indistinguishable from a healthy one if you only probe once.

Five moving parts:

  1. identity          an *enrolled* WARP key, preflighted against Cloudflare's
                       own control endpoints. This is first because it is the one
                       thing that decides real results from meaningless ones.
  2. port discovery    which of the 50+ WARP UDP ports leave this box at all
  3. sweep             one real handshake against sampled addresses on those ports
  4. verify            several spaced handshakes per survivor, measuring latency,
                       jitter and loss, then scoring the three together
  5. watchdog          a small constant re-check of the endpoints already in use,
                       so a filtered address is retired within a couple of minutes
                       instead of at the next full sweep

One rule runs through all of it: nothing a user waits on may ever wait on a
scan. A sweep already in flight is *joined* rather than refused, every outcome
comes back as a distinct report instead of a bare zero, and if the pool is empty
a scan is kicked off in the background while the caller immediately gets the
long-lived defaults.

Why the identity comes first
---------------------------
Cloudflare's responder decrypts a handshake initiation to learn which client is
calling and drops the packet without a word if that public key is not an enrolled
WARP device. A scan signed with a key Cloudflare does not know does not look
slow, it looks like the entire internet is dead. That is exactly what a stale
cached registration produced here: forty-eight addresses swept, zero answered,
every time, forever. ``identity()`` now proves the key gets answers before a
single candidate is measured, and falls back to WarpEP's enrolled probing key
when registration is impossible - which on an Iranian VPS it usually is.

The address space itself lives in ``bot.warpep``, which is the bridge to the
WarpEP scanner: same prefixes, same port ladder, same per-prefix sampling, and
IPv6 as a first-class family rather than an afterthought. The probing primitives
are exposed publicly (``measure``, ``fast_pass``, ``verify_rows``,
``discover_ports_for``) so ``bot.warppool`` can build the per-family pools on top
of this engine instead of standing up a second one beside it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, field, replace
from typing import Optional

from . import db, warp, warpep, warpstore, wireguard
from .config import settings
from .warpep import V4, V6
from .warptune import TUNE

log = logging.getLogger("autovless.warpscan")

IDENTITY_OPTION = "warp_scanner_identity"

# Cloudflare WARP endpoint pools, straight from the WarpEP bridge. Kept under the
# old names because scripts and older imports reach for them.
PREFIXES_V4: tuple[str, ...] = warpep.IPV4_PREFIXES
PREFIXES_V6: tuple[str, ...] = warpep.IPV6_PREFIXES

# Ports WARP listens on. The first few are the ones that usually survive.
COMMON_PORTS: tuple[int, ...] = warpep.PRIMARY_PORTS
ALL_PORTS: tuple[int, ...] = warpep.ALL_PORTS


def sample_addresses(per_prefix: int, family: str = V4) -> list[str]:
    """Random addresses spread evenly over the WARP pools of one family."""
    return warpep.candidates(family, per_prefix)


def _subnet_of(ip: str) -> str:
    """Group key used to spread a user's endpoints over different blocks."""
    return warpep.block_of(ip)


@dataclass
class ScanReport:
    """What happened on a sweep, in a shape a handler can render directly.

    ``status`` is the whole point of this class:

      done        the sweep ran here and now
      joined      a sweep was already in flight and we waited for its result
      cooldown    too soon since the last one; ``wait`` says how many seconds
      unreachable this host has no route for that family at all
      failed      something broke; ``reason`` is safe to show
      disabled    the feature is switched off

    ``note`` is the diagnosis when a sweep ran and still found nothing, which
    used to be reported as a bare zero that told nobody anything:

      no_route  the kernel has no route for this family
      identity  Cloudflare is not answering our key, so nothing can be found
      filtered  the key works elsewhere but this network drops WARP
    """

    status: str = "done"
    family: str = V4
    families: tuple[str, ...] = ()
    found: int = 0
    alive: int = 0
    best: Optional[float] = None
    ports: tuple[int, ...] = ()
    elapsed: float = 0.0
    wait: int = 0
    rescued: bool = False
    reason: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"done", "joined"} and self.found > 0


class WarpScanner:
    def __init__(self) -> None:
        self._scan_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._side_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._identity_lock = asyncio.Lock()
        self._inflight: Optional[asyncio.Future] = None
        self._stop = asyncio.Event()
        self._identity: Optional[dict] = None
        self._finished_at: float = 0.0
        self.ports: tuple[int, ...] = tuple(settings.warp_ports) or COMMON_PORTS
        self.family_ports: dict[str, tuple[int, ...]] = {}
        # False means "we fell back to the hardcoded list", which is a very
        # different thing from "these ports were measured to work".
        self.ports_proven: dict[str, bool] = {}
        self.identity_source: str = ""
        self.identity_ok: Optional[bool] = None
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
        available = warpep.available_families(refresh=True)
        if not available:
            log.error(
                "this host has no route to Cloudflare over IPv4 or IPv6. "
                "No scan can find anything until that is fixed."
            )
        elif V6 not in available:
            log.warning(
                "no IPv6 route on this host, so the IPv6 pool will stay empty. "
                "On Docker put the container on the host network "
                "(network_mode: host) or enable IPv6 on its network."
            )
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
        """An identity Cloudflare will actually answer. Resolved once, then cached."""
        if self._identity:
            return self._identity
        async with self._identity_lock:
            if self._identity:
                return self._identity
            self._identity = await self._resolve_identity()
            return self._identity

    async def _resolve_identity(self) -> Optional[dict]:
        """Pick a probing identity, in the order that actually works.

        1. the identity cached in the db - but only if it still gets answers,
        2. a fresh registration against ``api.cloudflareclient.com``,
        3. WarpEP's enrolled probing identity, which needs no network at all.

        Step 1 used to be the *only* step, and that was the bug. Cloudflare
        silently drops handshakes from a device it has forgotten, so one revoked
        registration made every scan from then on report "48 swept, 0 answered"
        with no way to tell that from real filtering. Step 3 is what keeps a scan
        working on a box where the WARP API itself is blocked.
        """
        stored = await db.get_option(IDENTITY_OPTION)
        if stored:
            candidate: Optional[dict] = None
            try:
                candidate = json.loads(stored)
            except (ValueError, AttributeError):
                log.info("stored scanner identity is unreadable, registering a new one")
            if candidate and candidate.get("private_key") and candidate.get("peer_public_key"):
                if await self._identity_answers(candidate):
                    self.identity_source = candidate.get("source") or "registered (cached)"
                    self.identity_ok = True
                    log.info("scanner identity: %s", self.identity_source)
                    return candidate
                log.warning(
                    "the cached scanner identity is not answered by a single control "
                    "endpoint. Cloudflare has most likely dropped the device, so every "
                    "scan would report zero. Registering a new one."
                )

        try:
            fresh = await warp.provision()
        except warp.WarpError as error:
            log.warning("scanner identity could not be registered: %s", error)
        else:
            fresh["source"] = f"registered ({fresh.get('account_type', 'free')})"
            fresh["shared"] = False
            self.identity_ok = await self._identity_answers(fresh)
            if self.identity_ok:
                await db.set_option(IDENTITY_OPTION, json.dumps(fresh, ensure_ascii=False))
                self.identity_source = fresh["source"]
                log.info("scanner warp identity registered (%s)", fresh.get("account_type"))
                return fresh
            log.warning(
                "a freshly registered device is not answered either, falling back to "
                "the WarpEP probing identity"
            )

        spare = warpep.fallback_identity()
        self.identity_ok = await self._identity_answers(spare)
        self.identity_source = spare.get("source") or "warpep bundled"
        if self.identity_ok:
            log.info("scanner identity: %s", self.identity_source)
        else:
            log.error(
                "neither a registered device nor the bundled WarpEP identity gets an "
                "answer from any Cloudflare control endpoint. Outbound UDP is almost "
                "certainly blocked on this box; no scan can succeed until it is not."
            )
        return spare

    async def _identity_answers(self, identity: dict) -> bool:
        """Does Cloudflare answer this key at all? Asked against its own endpoints.

        A handful of packets, and the only way to tell "this key is not enrolled"
        apart from "this network filters WARP". Without it a scan cannot report
        the difference, and a bare zero is exactly the report nobody can act on.
        """
        pairs: list[tuple[str, int]] = []
        for family in warpep.available_families():
            pairs.extend(warpep.CONTROL.get(family, ())[:2])
        if not pairs:
            return False
        semaphore = asyncio.Semaphore(8)
        results = await asyncio.gather(
            *(self._probe_once(host, port, identity, semaphore) for host, port in pairs),
            return_exceptions=True,
        )
        return any(
            not isinstance(item, BaseException) and item is not None for item in results
        )

    async def recheck_identity(self) -> bool:
        """Throw the cached identity away and resolve a new one. For the panel."""
        async with self._identity_lock:
            self._identity = None
            self.identity_ok = None
            self.identity_source = ""
        identity = await self.identity()
        return bool(identity and self.identity_ok)

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
            "family": warpep.family_of(host),
            "latency": round(latency, 1),
            "jitter": round(jitter, 1),
            "loss": round(loss, 3),
            "score": warpstore.score_of(latency, jitter, loss),
            "health": warpep.health(latency, jitter, loss),
            "stable": loss <= TUNE.loss_max,
        }

    # -- public probing surface, used by bot.warppool -------------------- #

    async def measure(
        self,
        host: str,
        port: int,
        probes: Optional[int] = None,
        identity: Optional[dict] = None,
    ) -> Optional[dict]:
        """Measure one endpoint. ``None`` means it never answered."""
        if not warpep.reachable(warpep.family_of(host)):
            return None
        identity = identity or await self.identity()
        if identity is None:
            return None
        return await self._measure(
            str(host), int(port), identity, asyncio.Semaphore(2), probes=probes
        )

    async def fast_pass(
        self,
        addresses: list[str],
        ports: list[int],
        identity: Optional[dict] = None,
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> dict[str, dict]:
        """One handshake per address and port. Keeps the fastest port per address."""
        identity = identity or await self.identity()
        if identity is None:
            return {}
        semaphore = semaphore or asyncio.Semaphore(settings.warp_scan_concurrency)
        return await self._fast_pass(list(addresses), list(ports), identity, semaphore)

    async def verify_rows(
        self,
        shortlist: list[dict],
        identity: Optional[dict] = None,
    ) -> list[dict]:
        """Second, spaced opinion on a shortlist, with jitter and loss."""
        identity = identity or await self.identity()
        if identity is None:
            return []
        return await self._verify_pass(shortlist, identity)

    async def discover_ports_for(
        self,
        family: str,
        identity: Optional[dict] = None,
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> list[int]:
        """Which WARP ports get out of this network, for one address family.

        Asked per family on purpose: an ISP that drops UDP 2408 over IPv4 quite
        often leaves the same port alone over IPv6, and assuming otherwise is how
        an IPv6 pool ends up empty for no reason.

        ``ports_proven[family]`` records whether these ports were *measured* or
        merely assumed, because "2408 500 1701" in a report meant both and the
        second one is a symptom rather than a result.
        """
        code = warpep.normalise_family(family)
        if settings.warp_ports:
            ports = list(settings.warp_ports)
            self.family_ports[code] = tuple(ports)
            self.ports_proven[code] = False
            return ports

        if not warpep.reachable(code):
            self.family_ports[code] = ()
            self.ports_proven[code] = False
            return []

        identity = identity or await self.identity()
        if identity is None:
            self.ports_proven[code] = False
            return list(COMMON_PORTS[:3])
        semaphore = semaphore or asyncio.Semaphore(settings.warp_scan_concurrency)

        probes = warpep.candidates(code, 2)[:4]
        controls = [host for host, _ in warpep.CONTROL.get(code, ())][:2]
        probes = list(dict.fromkeys(probes + controls)) or controls
        for wave in (
            COMMON_PORTS,
            tuple(port for port in ALL_PORTS if port not in COMMON_PORTS),
        ):
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
                log.info("warp ports reachable over %s: %s", code, ordered)
                self.family_ports[code] = tuple(ordered[:6])
                self.ports_proven[code] = True
                return ordered[:6]
        log.warning(
            "no warp port answered over %s. Either the probing identity is not "
            "enrolled or this network drops WARP entirely; assuming the common list.",
            code,
        )
        self.family_ports[code] = tuple(COMMON_PORTS[:3])
        self.ports_proven[code] = False
        return list(COMMON_PORTS[:3])

    async def discover_ports(self, identity: dict, semaphore: asyncio.Semaphore) -> list[int]:
        """IPv4 port discovery, kept for the legacy sweep path."""
        return await self.discover_ports_for(V4, identity, semaphore)

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
                best[host] = {
                    "ip": host,
                    "port": int(port),
                    "family": warpep.family_of(host),
                    "latency": float(rtt),
                }
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

    async def _rescue(self, identity: dict, family: str = V4) -> list[dict]:
        """Last resort: measure the published defaults for this family.

        Family-aware on purpose. The old version always measured the IPv4
        fallback list, so an IPv6 sweep that found nothing was rescued with four
        IPv4 addresses that the IPv6 pool could never use.
        """
        code = warpep.normalise_family(family)
        targets: tuple[tuple[str, int], ...] = warpep.CONTROL.get(code, ())
        if code == V4:
            targets = tuple(dict.fromkeys(targets + warp.FALLBACK_ENDPOINTS))
        if not targets:
            return []
        semaphore = asyncio.Semaphore(8)
        results = await asyncio.gather(
            *(
                self._measure(host, port, identity, semaphore, probes=2)
                for host, port in targets
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
        family: Optional[str] = None,
    ) -> ScanReport:
        """Run a sweep, or join the one already running. Never raises.

        This is the method the rescan button calls. ``family=None`` now means
        *every family this host can reach* rather than IPv4: the old default
        silently pinned the admin scan to IPv4, so pressing it could never put a
        single address into the IPv6 pool no matter how long anybody waited.
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
            if family is None:
                report = await self._sweep_all(quick=quick, sample=sample)
            else:
                report = await self._sweep(quick=quick, sample=sample, family=family)
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

    async def _sweep_all(
        self,
        quick: bool = False,
        sample: Optional[int] = None,
    ) -> ScanReport:
        """Sweep both families and merge the outcome into one report.

        Sequential rather than parallel: two sweeps racing for the same socket
        budget measure each other's congestion instead of the endpoints.
        """
        merged = ScanReport(status="done")
        parts: list[ScanReport] = []
        for code in warpep.FAMILIES:
            if not warpep.reachable(code):
                parts.append(
                    ScanReport(
                        status="unreachable",
                        family=code,
                        note="no_route",
                        reason=f"no {code} route on this host",
                    )
                )
                continue
            parts.append(await self._sweep(quick=quick, sample=sample, family=code))

        done = [part for part in parts if part.status == "done"]
        merged.families = tuple(part.family for part in done)
        merged.alive = sum(part.alive for part in parts)
        merged.found = max((part.found for part in parts), default=0)
        merged.elapsed = round(sum(part.elapsed for part in parts), 1)
        merged.ports = tuple(dict.fromkeys(port for part in parts for port in part.ports))
        pings = [part.best for part in parts if part.best]
        merged.best = min(pings) if pings else None
        merged.rescued = any(part.rescued for part in parts)
        if not done:
            merged.status = parts[0].status if parts else "failed"
            merged.note = parts[0].note if parts else ""
            merged.reason = "; ".join(part.reason for part in parts if part.reason)[:180]
        elif not merged.alive:
            merged.note = next((part.note for part in done if part.note), "filtered")
        return merged

    async def _sweep(
        self,
        quick: bool = False,
        sample: Optional[int] = None,
        family: str = V4,
    ) -> ScanReport:
        started = time.perf_counter()
        code = warpep.normalise_family(family)
        if not warpep.reachable(code):
            return ScanReport(
                status="unreachable",
                family=code,
                note="no_route",
                reason=f"no {code} route on this host",
            )
        async with self._lock:
            self.running = True
            try:
                identity = await self.identity()
                if identity is None:
                    return ScanReport(
                        status="failed",
                        family=code,
                        note="identity",
                        reason="warp identity unavailable",
                    )

                await warpstore.ensure_schema()
                semaphore = asyncio.Semaphore(settings.warp_scan_concurrency)

                ports = await self.discover_ports_for(code, identity, semaphore)
                if not ports:
                    return ScanReport(
                        status="unreachable",
                        family=code,
                        note="no_route",
                        reason=f"no {code} route on this host",
                    )
                self.ports = tuple(ports)

                per_prefix = sample or (
                    TUNE.quick_sample if quick else settings.warp_scan_sample
                )
                candidates = warpep.candidates(code, per_prefix)
                answered = await self._fast_pass(candidates, list(ports[:3]), identity, semaphore)

                shortlist = sorted(answered.values(), key=lambda row: row["latency"])
                shortlist = shortlist[: settings.warp_verify_top]
                verified = await self._verify_pass(shortlist, identity)

                stable = [row for row in verified if row.get("stable")]
                rescued = False
                if not stable:
                    # Nothing survived. Keep the shaky rows if there are any, and
                    # fall back to this family's published endpoints so a cold
                    # pool is never left with literally nothing.
                    stable = verified or await self._rescue(identity, code)
                    rescued = not verified and bool(stable)
                    if stable:
                        log.info("warp sweep found nothing stable, kept %s rows", len(stable))

                if stable:
                    await warpstore.upsert(stable)
                retired = await warpstore.retire()
                # Per family. A single global cap ranked both families in one
                # list, so a busy IPv4 pool could evict every IPv6 row the sweep
                # had just found and the IPv6 pool stayed at zero for ever.
                await warpstore.trim(settings.warp_pool_size, family=code)

                pool = await warpstore.stats()
                elapsed = time.perf_counter() - started
                self.last_run = db.now()
                self.last_found = int(pool["stable"]) or len(stable)

                note = ""
                if not answered:
                    note = "identity" if self.identity_ok is False else "filtered"

                await db.log_event(
                    "warp_scan",
                    detail=(
                        f"family={code} mode={'quick' if quick else 'full'} "
                        f"swept={len(candidates)} alive={len(answered)} "
                        f"verified={len(verified)} stored={len(stable)} "
                        f"pool={pool['stable']}/{pool['total']} retired={retired} "
                        f"ports={','.join(str(p) for p in ports[:3])} "
                        f"identity={self.identity_source or '?'} "
                        f"note={note or 'ok'} elapsed={elapsed:.1f}s"
                    ),
                )
                log.info(
                    "warp scan (%s): %s answered, %s verified, %s stored, pool %s stable",
                    code,
                    len(answered),
                    len(verified),
                    len(stable),
                    pool["stable"],
                )
                return ScanReport(
                    status="done",
                    family=code,
                    families=(code,),
                    found=self.last_found,
                    alive=len(answered),
                    best=pool.get("best"),
                    ports=self.ports,
                    elapsed=round(elapsed, 1),
                    rescued=rescued,
                    note=note,
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
                    "warp watchdog: %s went quiet (%s strikes)",
                    warpep.host_port(row["ip"], row["port"]),
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
                "family": warpep.family_of(host),
                "latency": 0.0,
                "jitter": 0.0,
                "loss": 0.0,
                "score": 0.0,
                "health": 0,
                "stable": False,
            }
            for host, port in warp.FALLBACK_ENDPOINTS[: max(1, count)]
        ]

    async def _pool(self, count: int) -> list[dict]:
        # Pinned to IPv4 on purpose. This feeds the legacy export renderers in
        # ``bot.warp``, which format an endpoint as ``host:port`` and would emit a
        # broken line for an IPv6 literal. Anything that needs both families goes
        # through ``bot.warppool`` and ``bot.warpconf`` instead.
        rows = await warpstore.best(
            count * 6, stable_only=True, max_loss=TUNE.loss_max, family=V4
        )
        if len(rows) < count:
            seen = {(row["ip"], row["port"]) for row in rows}
            rows += [
                row
                for row in await warpstore.best(count * 6, stable_only=False, family=V4)
                if (row["ip"], row["port"]) not in seen
            ]
        return rows

    def _spread(self, rows: list[dict], count: int) -> list[dict]:
        """Spread the picks over blocks so one bad /24 cannot sink a user."""
        return warpep.spread(rows, count)

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
            log.info(
                "warp failover: %s is gone, switching",
                warpep.host_port(head.get("ip", "?"), head.get("port", 0)),
            )
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
        data["source"] = warpep.describe()
        data["identity"] = self.identity_source
        data["identity_ok"] = self.identity_ok
        data["routes"] = warpep.routes()
        return data

    async def snapshot(self, limit: Optional[int] = None) -> list[dict]:
        return await warpstore.snapshot(limit)


warp_scanner = WarpScanner()
