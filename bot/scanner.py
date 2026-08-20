"""Clean IP scanner for Cloudflare edge ranges.

Two stages, tuned for a 1 vCPU / 1 GB box:
  1. cheap TCP connect sweep over random addresses inside Cloudflare prefixes
  2. verification of the fastest candidates with a real HTTP request, which
     also reveals the edge colo through the cf-ray header
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import ssl
import time
from typing import Iterable, Optional

from . import db
from .config import settings

log = logging.getLogger("autovless.scanner")

# Cloudflare published IPv4 prefixes.
CF_PREFIXES: tuple[str, ...] = (
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "108.162.192.0/18",
    "131.0.72.0/22",
    "141.101.64.0/18",
    "162.158.0.0/15",
    "172.64.0.0/13",
    "173.245.48.0/20",
    "188.114.96.0/20",
    "190.93.240.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
)

TRACE_HOST = "cloudflare.com"
_NETWORKS = [ipaddress.ip_network(prefix) for prefix in CF_PREFIXES]
_WEIGHTS = [net.num_addresses for net in _NETWORKS]


def random_ips(count: int) -> list[str]:
    """Sample addresses across Cloudflare prefixes, weighted by prefix size."""
    picked: set[str] = set()
    guard = 0
    while len(picked) < count and guard < count * 8:
        guard += 1
        net = random.choices(_NETWORKS, weights=_WEIGHTS, k=1)[0]
        offset = random.randint(1, max(1, net.num_addresses - 2))
        picked.add(str(net.network_address + offset))
    return list(picked)


class CleanIPScanner:
    def __init__(self) -> None:
        self.ports: tuple[int, ...] = tuple(dict.fromkeys(settings.tls_ports + settings.http_ports))
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self.last_run: int = 0
        self.last_found: int = 0
        self.running: bool = False

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="clean-ip-scanner")
            log.info("scanner started (ports=%s interval=%ss)", self.ports, settings.scan_interval)

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
        # Warm the pool immediately so the first user never waits on an empty set.
        while not self._stop.is_set():
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("scan cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.scan_interval)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------ #
    # scanning
    # ------------------------------------------------------------------ #

    async def scan_once(self, batch: Optional[int] = None) -> int:
        """Run one full sweep. Returns the number of verified endpoints stored."""
        if self._lock.locked():
            return 0

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            batch = batch or settings.scan_batch
            semaphore = asyncio.Semaphore(settings.scan_concurrency)
            stored = 0

            try:
                for port in self.ports:
                    candidates = random_ips(batch)
                    results = await asyncio.gather(
                        *(self._tcp_probe(ip, port, semaphore) for ip in candidates),
                        return_exceptions=False,
                    )
                    alive = sorted((r for r in results if r), key=lambda r: r["latency"])
                    shortlist = alive[: settings.verify_top]

                    verify_sem = asyncio.Semaphore(min(24, settings.scan_concurrency))
                    verified = await asyncio.gather(
                        *(self._verify(item, verify_sem) for item in shortlist),
                        return_exceptions=False,
                    )
                    good = [v for v in verified if v]
                    await db.store_clean_ips(good)
                    stored += len(good)
                    log.info("port %s: %s alive, %s verified", port, len(alive), len(good))

                await db.trim_pool(settings.pool_size)
                self.last_run = db.now()
                self.last_found = stored
                await db.log_event(
                    "scan",
                    detail=f"stored={stored} elapsed={time.perf_counter() - started:.1f}s",
                )
                return stored
            finally:
                self.running = False

    async def _tcp_probe(self, ip: str, port: int, semaphore: asyncio.Semaphore) -> Optional[dict]:
        async with semaphore:
            start = time.perf_counter()
            writer = None
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), timeout=settings.scan_timeout
                )
            except (OSError, asyncio.TimeoutError):
                return None
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (OSError, asyncio.TimeoutError):
                        pass
            return {"ip": ip, "port": port, "latency": (time.perf_counter() - start) * 1000}

    async def _verify(self, candidate: dict, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """Confirm the address is a live Cloudflare edge and read its colo."""
        ip, port = candidate["ip"], int(candidate["port"])
        use_tls = port in settings.tls_ports

        async with semaphore:
            start = time.perf_counter()
            writer = None
            try:
                if use_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    coro = asyncio.open_connection(ip, port, ssl=context, server_hostname=TRACE_HOST)
                else:
                    coro = asyncio.open_connection(ip, port)
                reader, writer = await asyncio.wait_for(coro, timeout=settings.scan_timeout * 3)

                request = (
                    f"GET /cdn-cgi/trace HTTP/1.1\r\n"
                    f"Host: {TRACE_HOST}\r\n"
                    f"User-Agent: {settings.brand}/1.0\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("ascii")
                writer.write(request)
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(4096), timeout=settings.scan_timeout * 3)
            except (OSError, asyncio.TimeoutError, ssl.SSLError):
                return None
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (OSError, asyncio.TimeoutError, ssl.SSLError):
                        pass

        latency = (time.perf_counter() - start) * 1000
        text = raw.decode("latin-1", errors="ignore")
        colo = _extract_colo(text)
        if colo is None:
            return None

        return {
            "ip": ip,
            "port": port,
            "latency": round(min(latency, candidate["latency"] * 4), 1),
            "colo": colo,
            "verified": True,
        }

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def stats(self) -> dict:
        pool = await db.pool_stats()
        pool["scanning"] = self.running
        pool["last_run"] = self.last_run
        pool["ports"] = list(self.ports)
        return pool

    async def pick(self, port: int, count: int) -> list[dict]:
        """Best verified endpoints for a port, with a graceful fallback."""
        rows = await db.best_ips(port, count, verified_only=True)
        if len(rows) < count:
            rows += [
                r
                for r in await db.best_ips(port, count * 3, verified_only=False)
                if r["ip"] not in {x["ip"] for x in rows}
            ][: count - len(rows)]
        return rows[:count]


def _extract_colo(response: str) -> Optional[str]:
    lowered = response.lower()
    if "cf-ray:" in lowered:
        start = lowered.index("cf-ray:") + len("cf-ray:")
        line = response[start : response.find("\n", start)].strip()
        if "-" in line:
            colo = line.rsplit("-", 1)[-1].strip().upper()
            if colo.isalpha() and 2 <= len(colo) <= 4:
                return colo
    if "colo=" in lowered:
        start = lowered.index("colo=") + len("colo=")
        colo = response[start : start + 6].split()[0].strip().upper()
        if colo.isalpha():
            return colo
    if "server: cloudflare" in lowered:
        return "CF"
    return None


scanner = CleanIPScanner()
