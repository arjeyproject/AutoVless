"""Clean IP and proxyIP scanners.

Two independent background jobs, both tuned for a 1 vCPU / 1 GB box:

  CleanIPScanner   entry points the client dials. Three sources feed it:
                   curated public lists, self-healing clean-IP hostnames, and a
                   weighted random sweep of Cloudflare's prefixes. Survivors are
                   verified twice through /cdn-cgi/trace so latency and jitter
                   are both real, then scored and stored per port.

  ProxyIPScanner   relays the worker uses to reach hosts that sit behind
                   Cloudflare. A Worker cannot open a socket to a
                   Cloudflare-owned address, so anything resolving into a
                   Cloudflare prefix is rejected outright.

Why per-port matters: a config on port 80 is only as good as a port 80 probe.
Every port keeps its own target and its own slice of the pool, so the plain
HTTP configs are never shipped on addresses that were only ever tested on 443.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import re
import socket
import ssl
import time
from typing import Optional

import httpx

from . import db, proxies
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

_HOST_PATTERN = re.compile(
    r"\b((?:\d{1,3}\.){3}\d{1,3}|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})(?::(\d{2,5}))?",
    re.IGNORECASE,
)
_SOURCE_NOISE = (
    "github.com",
    "githubusercontent.com",
    "t.me",
    "telegram.org",
    "cloudflare.com",
    "example.com",
    "README.md",
)


def is_cloudflare(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in net for net in _NETWORKS)


def subnet_of(address: str) -> str:
    """The /24 an address belongs to, or the hostname itself for domains."""
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return address.lower()
    return address.rsplit(".", 1)[0]


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


async def fetch_list(url: str) -> list[tuple[str, Optional[int]]]:
    """Pull a community list and pick every host / host:port pair out of it."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": f"{settings.brand}/1.1"})
        if response.status_code != 200:
            return []
        body = response.text
    except Exception:  # noqa: BLE001
        log.debug("list fetch failed: %s", url)
        return []

    found: list[tuple[str, Optional[int]]] = []
    seen: set[str] = set()
    for match in _HOST_PATTERN.finditer(body):
        host = match.group(1).strip().lower()
        port = int(match.group(2)) if match.group(2) else None
        if host in seen or any(noise.lower() in host for noise in _SOURCE_NOISE):
            continue
        seen.add(host)
        found.append((host, port))
    return found


async def resolve(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM),
            timeout=6.0,
        )
    except (OSError, asyncio.TimeoutError, socket.gaierror):
        return []
    return list(dict.fromkeys(info[4][0] for info in infos))


def _extract_colo(response: str) -> Optional[str]:
    lowered = response.lower()
    if "cf-ray:" in lowered:
        start = lowered.index("cf-ray:") + len("cf-ray:")
        end = response.find("\n", start)
        line = response[start : end if end != -1 else len(response)].strip()
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


def _ok_status(response: str) -> bool:
    head = response[:16].upper()
    return head.startswith("HTTP/") and (" 200" in response[:24] or " 30" in response[:24])


async def trace_probe(
    host: str,
    port: int,
    use_tls: bool,
    timeout: float,
    sni: str = TRACE_HOST,
) -> Optional[dict]:
    """Fetch /cdn-cgi/trace through host:port and report latency plus colo."""
    start = time.perf_counter()
    writer = None
    try:
        if use_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.set_alpn_protocols(["http/1.1"])
            coro = asyncio.open_connection(host, port, ssl=context, server_hostname=sni)
        else:
            coro = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(coro, timeout=timeout)

        request = (
            "GET /cdn-cgi/trace HTTP/1.1\r\n"
            f"Host: {sni}\r\n"
            f"User-Agent: {settings.brand}/1.1\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(request)
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
    except (OSError, asyncio.TimeoutError, ssl.SSLError, ValueError):
        return None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError, ssl.SSLError):
                pass

    text = raw.decode("latin-1", errors="ignore")
    if not text or not _ok_status(text):
        return None
    colo = _extract_colo(text)
    if colo is None:
        return None
    return {"latency": round((time.perf_counter() - start) * 1000, 1), "colo": colo}


def score_of(latency: float, jitter: float, kind: str) -> float:
    """One number the whole pool can be ranked by.

    Jitter is weighted heavily on purpose: an address that answers in 90 ms and
    then 900 ms is a worse entry point than one that always answers in 300 ms.
    Self-healing hostnames get a small credit because the address behind them
    keeps being replaced upstream, so they age far better than a raw IP.
    """
    base = float(latency) + (float(jitter) * 2.0)
    if kind == "domain":
        base -= 60.0
    return round(max(1.0, base), 1)


# ===================================================================== #
# clean entry points
# ===================================================================== #


class CleanIPScanner:
    def __init__(self) -> None:
        self.ports: tuple[int, ...] = settings.all_ports
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._seeds: list[str] = []
        self._seeds_at: float = 0.0
        self.last_run: int = 0
        self.last_found: int = 0
        self.waves: int = 0
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
    # candidate sources
    # ------------------------------------------------------------------ #

    async def seeds(self) -> list[str]:
        """Curated addresses from public lists, refreshed at most hourly.

        A purely random sweep mostly finds edges on the other side of the
        planet. Seeding with known-good addresses is what makes the first
        build usable instead of merely reachable.
        """
        if self._seeds and (time.time() - self._seeds_at) < 3600:
            return self._seeds
        found: list[str] = []
        for url in settings.clean_ip_sources:
            for host, _port in await fetch_list(url):
                if is_cloudflare(host):
                    found.append(host)
        self._seeds = list(dict.fromkeys(found))[:400]
        self._seeds_at = time.time()
        if self._seeds:
            log.info("loaded %s seed addresses", len(self._seeds))
        return self._seeds

    # ------------------------------------------------------------------ #
    # scanning
    # ------------------------------------------------------------------ #

    async def scan_once(self, batch: Optional[int] = None) -> int:
        """Run one full sweep. Returns the number of verified endpoints stored.

        Ports are swept in parallel and each one keeps going, with a bigger
        random batch every time, until it holds enough verified addresses of its
        own or the wave budget runs out.
        """
        if self._lock.locked():
            return 0

        async with self._lock:
            self.running = True
            self.waves = 0
            started = time.perf_counter()
            base_batch = batch or settings.scan_batch
            semaphore = asyncio.Semaphore(settings.scan_concurrency)
            verify_sem = asyncio.Semaphore(max(8, min(24, settings.scan_concurrency // 4)))
            seeds = await self.seeds()
            stored = 0

            try:
                pending = list(self.ports)
                for wave in range(settings.scan_waves):
                    if not pending:
                        break
                    self.waves = wave + 1
                    size = int(base_batch * (1 + wave))
                    results = await asyncio.gather(
                        *(
                            self._sweep_port(port, size, seeds, wave, semaphore, verify_sem)
                            for port in pending
                        ),
                        return_exceptions=True,
                    )
                    still: list[int] = []
                    for port, outcome in zip(pending, results):
                        if isinstance(outcome, BaseException):
                            log.warning("port %s sweep failed: %s", port, outcome)
                            still.append(port)
                            continue
                        stored += outcome
                        coverage = await db.best_ips(port, settings.scan_min_verified)
                        if len(coverage) < settings.scan_min_verified:
                            still.append(port)
                    pending = still

                await db.trim_pool(settings.pool_size)
                self.last_run = db.now()
                self.last_found = stored
                await db.log_event(
                    "scan",
                    detail=(
                        f"stored={stored} waves={self.waves} "
                        f"short={','.join(str(p) for p in pending) or '-'} "
                        f"elapsed={time.perf_counter() - started:.1f}s"
                    ),
                )
                return stored
            finally:
                self.running = False

    async def _sweep_port(
        self,
        port: int,
        batch: int,
        seeds: list[str],
        wave: int,
        semaphore: asyncio.Semaphore,
        verify_sem: asyncio.Semaphore,
    ) -> int:
        """One pass over a single port: connect, shortlist, verify, store."""
        candidates: list[tuple[str, str]] = []
        if wave == 0:
            candidates += [(domain, "domain") for domain in settings.clean_domains]
            candidates += [(ip, "ip") for ip in seeds]
        candidates += [(ip, "ip") for ip in random_ips(batch)]

        unique: dict[str, str] = {}
        for host, kind in candidates:
            unique.setdefault(host, kind)

        alive = await asyncio.gather(
            *(self._tcp_probe(host, port, kind, semaphore) for host, kind in unique.items())
        )
        found = [item for item in alive if item]
        if not found:
            return 0

        # Hostnames are cheap to keep and age well, so they always get verified.
        domains = [item for item in found if item["kind"] == "domain"]
        addresses = sorted(
            (item for item in found if item["kind"] != "domain"), key=lambda r: r["latency"]
        )
        shortlist = domains + addresses[: settings.verify_top]

        verified = await asyncio.gather(
            *(self._verify(item, port, verify_sem) for item in shortlist)
        )
        good = [item for item in verified if item]
        await db.store_clean_ips(good)
        log.info(
            "port %s wave %s: %s alive, %s verified (%s hostnames)",
            port,
            wave + 1,
            len(found),
            len(good),
            sum(1 for item in good if item["kind"] == "domain"),
        )
        return len(good)

    async def _tcp_probe(
        self,
        host: str,
        port: int,
        kind: str,
        semaphore: asyncio.Semaphore,
    ) -> Optional[dict]:
        async with semaphore:
            start = time.perf_counter()
            writer = None
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=settings.scan_timeout
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
            return {
                "ip": host,
                "port": port,
                "kind": kind,
                "latency": (time.perf_counter() - start) * 1000,
            }

    async def _verify(
        self,
        candidate: dict,
        port: int,
        semaphore: asyncio.Semaphore,
    ) -> Optional[dict]:
        """Confirm this is a live Cloudflare edge, twice, and measure the spread.

        A single probe cannot tell a genuinely fast edge from one that answered
        once and then stalls. Every probe has to succeed; the gap between them
        becomes the jitter that feeds the score.
        """
        host = candidate["ip"]
        kind = candidate.get("kind") or "ip"
        use_tls = port in settings.tls_ports
        timeout = settings.scan_timeout * 3
        samples: list[float] = []
        colo: Optional[str] = None

        async with semaphore:
            for attempt in range(settings.verify_probes):
                if attempt:
                    await asyncio.sleep(0.25)
                result = await trace_probe(host, port, use_tls, timeout)
                if result is None:
                    return None
                samples.append(float(result["latency"]))
                colo = colo or result["colo"]

        if not samples:
            return None
        latency = round(sum(samples) / len(samples), 1)
        jitter = round(max(samples) - min(samples), 1)
        return {
            "ip": host,
            "port": port,
            "kind": kind,
            "latency": latency,
            "jitter": jitter,
            "score": score_of(latency, jitter, kind),
            "colo": colo or "CF",
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
        pool["coverage"] = await db.port_coverage()
        return pool

    async def pick(self, port: int, count: int, verified_only: bool = True) -> list[dict]:
        """Best verified endpoints for a port, spread over different /24s.

        Handing a user six addresses out of one subnet is the same as handing
        them one address: when that block gets throttled, every config dies at
        the same moment.
        """
        rows = await db.best_ips(port, max(count * 8, 24), verified_only=True)
        if len(rows) < count and not verified_only:
            known = {row["ip"] for row in rows}
            rows += [
                row
                for row in await db.best_ips(port, count * 8, verified_only=False)
                if row["ip"] not in known
            ]

        spread: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            subnet = subnet_of(str(row["ip"]))
            if subnet in seen:
                continue
            seen.add(subnet)
            spread.append(row)
            if len(spread) >= count:
                return spread

        for row in rows:  # relax the spread rather than return short
            if len(spread) >= count:
                break
            if row not in spread:
                spread.append(row)
        return spread[:count]

    async def demote(self, ip: str, port: int) -> None:
        """Called when a shipped endpoint turns out to be unreachable."""
        await db.mark_ip_fail(ip, port)


# ===================================================================== #
# proxyIP relays
# ===================================================================== #


class ProxyIPScanner:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self.running: bool = False
        self.last_run: int = 0

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="proxy-ip-scanner")
            log.info("proxy scanner started (interval=%ss)", settings.proxy_scan_interval)

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
                log.exception("proxy scan cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.proxy_scan_interval)
            except asyncio.TimeoutError:
                continue

    async def candidates(self) -> list[tuple[str, int]]:
        default_port = settings.proxy_ports[0] if settings.proxy_ports else 443
        out: list[tuple[str, int]] = []

        for raw in settings.proxy_seeds:
            host, _, port = raw.partition(":")
            out.append((host.strip().lower(), int(port) if port.isdigit() else default_port))

        for url in settings.proxy_sources:
            for host, port in await fetch_list(url):
                out.append((host, port or default_port))

        # Keep whatever already proved itself in the rotation.
        for row in await proxies.best(settings.proxy_pool_size, verified_only=False):
            out.append((row["host"], int(row["port"])))

        unique: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for item in out:
            if not item[0] or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique[: settings.proxy_scan_limit]

    async def scan_once(self) -> int:
        if self._lock.locked():
            return 0

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            try:
                candidates = await self.candidates()
                if not candidates:
                    return 0

                semaphore = asyncio.Semaphore(min(48, settings.scan_concurrency))
                results = await asyncio.gather(
                    *(self._verify(host, port, semaphore) for host, port in candidates),
                    return_exceptions=False,
                )
                good = [r for r in results if r]
                await proxies.store(good)
                await proxies.trim(settings.proxy_pool_size * 2)
                self.last_run = db.now()
                await db.log_event(
                    "proxy_scan",
                    detail=(
                        f"checked={len(candidates)} ok={len(good)} "
                        f"elapsed={time.perf_counter() - started:.1f}s"
                    ),
                )
                log.info("proxy scan: %s checked, %s usable", len(candidates), len(good))
                return len(good)
            finally:
                self.running = False

    async def _verify(self, host: str, port: int, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """A usable relay forwards TCP to the Cloudflare edge and is not itself
        a Cloudflare address, because Workers cannot dial those."""
        async with semaphore:
            addresses = await resolve(host)
            if not addresses:
                return None
            if all(is_cloudflare(address) for address in addresses):
                return None

            result = await trace_probe(host, port, use_tls=True, timeout=6.0)

        if result is None:
            return None
        return {
            "host": host,
            "port": port,
            "latency": result["latency"],
            "colo": result["colo"],
            "verified": True,
        }

    async def pick(self, count: int) -> list[dict]:
        rows = await proxies.best(count, verified_only=True)
        if len(rows) < count:
            known = {(row["host"], int(row["port"])) for row in rows}
            rows += [
                row
                for row in await proxies.best(count * 2, verified_only=False)
                if (row["host"], int(row["port"])) not in known
            ]
        return rows[:count]

    async def stats(self) -> dict:
        data = await proxies.stats()
        data["scanning"] = self.running
        data["last_run"] = self.last_run
        return data


scanner = CleanIPScanner()
proxy_scanner = ProxyIPScanner()
