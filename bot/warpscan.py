"""WARP endpoint engine.

Cloudflare hands out thousands of WARP endpoint addresses and every one of them
behaves differently from a given network. Iranian DPI makes this worse: some
endpoints answer the handshake and then get torn down a second later, which
looks identical to a working one if you only probe once.

So the engine works in three passes:

  1. port discovery  which of the 50+ WARP UDP ports this box can reach at all
  2. sweep           a real handshake against sampled addresses on those ports
  3. stability       a second, spaced handshake per survivor; anything that
                     stops answering is dropped instead of handed to a user

The scanner keeps its own throwaway WARP identity so nobody's personal account
is burned on probing.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import random
import time
from typing import Optional

from . import db, warp, wireguard
from .config import settings

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
        offsets = random.sample(range(1, size - 1), min(per_prefix, size - 2))
        picked.extend(str(network.network_address + offset) for offset in offsets)
    random.shuffle(picked)
    return picked


class WarpScanner:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._identity: Optional[dict] = None
        self.ports: tuple[int, ...] = tuple(settings.warp_ports) or COMMON_PORTS
        self.running: bool = False
        self.last_run: int = 0
        self.last_found: int = 0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if not settings.warp_enabled:
            log.info("warp engine disabled by configuration")
            return
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="warp-scanner")
            log.info("warp engine started (interval=%ss)", settings.warp_scan_interval)

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
        while not self._stop.is_set():
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("warp scan cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.warp_scan_interval)
            except asyncio.TimeoutError:
                continue

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

    async def _probe(
        self,
        host: str,
        port: int,
        identity: dict,
        semaphore: asyncio.Semaphore,
        attempts: int = 1,
    ) -> Optional[dict]:
        async with semaphore:
            if attempts > 1:
                rtt = await wireguard.stable_handshake(
                    host,
                    port,
                    identity["private_key"],
                    identity["peer_public_key"],
                    identity.get("reserved") or (0, 0, 0),
                    timeout=settings.warp_scan_timeout,
                    attempts=attempts,
                )
            else:
                rtt = await wireguard.handshake_rtt(
                    host,
                    port,
                    identity["private_key"],
                    identity["peer_public_key"],
                    identity.get("reserved") or (0, 0, 0),
                    timeout=settings.warp_scan_timeout,
                )
        if rtt is None:
            return None
        return {"ip": host, "port": port, "latency": rtt}

    async def discover_ports(self, identity: dict, semaphore: asyncio.Semaphore) -> list[int]:
        """Which WARP ports get out of this network. Cheap, and worth a lot."""
        if settings.warp_ports:
            return list(settings.warp_ports)

        probes = sample_addresses(1)[:4] or ["162.159.192.1"]
        for wave in (COMMON_PORTS, tuple(p for p in ALL_PORTS if p not in COMMON_PORTS)):
            results = await asyncio.gather(
                *(
                    self._probe(host, port, identity, semaphore)
                    for port in wave
                    for host in probes
                ),
                return_exceptions=False,
            )
            alive = sorted(
                {int(r["port"]) for r in results if r},
                key=lambda port: COMMON_PORTS.index(port) if port in COMMON_PORTS else 99,
            )
            if alive:
                log.info("warp ports reachable: %s", alive)
                return alive[:6]
        log.warning("no warp port answered, falling back to the common list")
        return list(COMMON_PORTS[:3])

    async def scan_once(self, sample: Optional[int] = None) -> int:
        """One full sweep. Returns how many stable endpoints were stored."""
        if self._lock.locked():
            return 0

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            try:
                identity = await self.identity()
                if identity is None:
                    return 0

                semaphore = asyncio.Semaphore(settings.warp_scan_concurrency)
                ports = await self.discover_ports(identity, semaphore)
                self.ports = tuple(ports)

                per_prefix = sample or settings.warp_scan_sample
                candidates = sample_addresses(per_prefix)
                results = await asyncio.gather(
                    *(
                        self._probe(host, port, identity, semaphore)
                        for host in candidates
                        for port in ports[:3]
                    ),
                    return_exceptions=False,
                )

                # One row per address: keep whichever port answered fastest.
                best_by_ip: dict[str, dict] = {}
                for row in (r for r in results if r):
                    current = best_by_ip.get(row["ip"])
                    if current is None or row["latency"] < current["latency"]:
                        best_by_ip[row["ip"]] = row

                shortlist = sorted(best_by_ip.values(), key=lambda r: r["latency"])
                shortlist = shortlist[: settings.warp_verify_top]

                verify_sem = asyncio.Semaphore(min(24, settings.warp_scan_concurrency))
                confirmed = await asyncio.gather(
                    *(
                        self._probe(row["ip"], row["port"], identity, verify_sem, attempts=3)
                        for row in shortlist
                    ),
                    return_exceptions=False,
                )

                stable = [dict(row, stable=True) for row in confirmed if row]
                await db.store_warp_endpoints(stable)
                await db.trim_warp_pool(settings.warp_pool_size)

                self.last_run = db.now()
                self.last_found = len(stable)
                await db.log_event(
                    "warp_scan",
                    detail=(
                        f"alive={len(best_by_ip)} stable={len(stable)} "
                        f"ports={','.join(str(p) for p in ports[:3])} "
                        f"elapsed={time.perf_counter() - started:.1f}s"
                    ),
                )
                log.info(
                    "warp scan: %s answered, %s survived the stability check",
                    len(best_by_ip),
                    len(stable),
                )
                return len(stable)
            finally:
                self.running = False

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def pick(self, count: Optional[int] = None) -> list[dict]:
        """Best endpoints, spread across pools so one bad subnet cannot sink a user."""
        count = count or settings.warp_per_config
        rows = await db.best_warp_endpoints(count * 6, stable_only=True)
        if len(rows) < count:
            rows += [
                row
                for row in await db.best_warp_endpoints(count * 6, stable_only=False)
                if row["ip"] not in {item["ip"] for item in rows}
            ]

        spread: list[dict] = []
        seen_subnets: set[str] = set()
        for row in rows:
            subnet = str(row["ip"]).rsplit(".", 1)[0]
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

    async def stats(self) -> dict:
        data = await db.warp_pool_stats()
        data["scanning"] = self.running
        data["last_run"] = self.last_run
        data["ports"] = list(self.ports)
        return data


warp_scanner = WarpScanner()
