"""Exhaustive, freshness-aware clean-IP and proxy relay scanners.

The clean-IP engine walks Cloudflare /24s with a persisted cursor instead of
repeatedly gambling on random addresses. Existing winners are rechecked, public
sources are parsed defensively, and every stored endpoint must complete several
real handshakes on the exact port that will be placed in user configs.

What "real" means changed, and it is the whole reason port 443 used to ship dead
configs. Verification now speaks the client's sentence: TLS with a live panel
hostname as the SNI, then a WebSocket upgrade on the panel's own path, and
nothing is stored as verified without a ``101``. See bot/probe.py. A trace
request to cloudflare.com is only used to warm a pool that has no panel to aim
at yet, because it proves the edge answers, not that your worker is reachable
through it.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import random
import re
import socket
import statistics
import time
from pathlib import Path
from typing import Optional

import httpx

from . import db, probe, proxies
from .config import BASE_DIR, settings
from .vless import WS_PATH

log = logging.getLogger("autovless.scanner")

CF_PREFIXES = (
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17",
)
_NETWORKS = tuple(ipaddress.ip_network(item) for item in CF_PREFIXES)
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.I)
_HTML = ("<!doctype", "<html", "<head", "<body", "<script")
_NOISE = ("github.com", "githubusercontent.com", "telegram.org", "t.me", "example.com")
REFERENCE_KEY = "verify_host"
REFERENCE_TTL = 300


def is_cloudflare(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(value in network for network in _NETWORKS)


def _subnet_key(host: str) -> str:
    try:
        return str(ipaddress.ip_network(f"{host}/24", strict=False).network_address)
    except ValueError:
        return host.lower()


def _all_subnets() -> list[int]:
    values: list[int] = []
    for network in _NETWORKS:
        values.extend(int(item.network_address) for item in network.subnets(new_prefix=24))
    random.Random(0xA17C0F).shuffle(values)
    return values


class SubnetSweeper:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.subnets = _all_subnets()
        self.cursor = 0
        self.laps = 0
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            self.cursor = int(state.get("cursor", 0)) % len(self.subnets)
            self.laps = max(0, int(state.get("laps", 0)))
        except (OSError, ValueError, TypeError, ZeroDivisionError):
            pass

    @property
    def progress(self) -> float:
        return round(self.cursor * 100 / max(1, len(self.subnets)), 1)

    def take(self, count: int, per_subnet: int) -> list[str]:
        out: list[str] = []
        per_subnet = max(1, min(8, per_subnet))
        while len(out) < count:
            base = self.subnets[self.cursor]
            self.cursor += 1
            if self.cursor >= len(self.subnets):
                self.cursor = 0
                self.laps += 1
            for offset in random.sample(range(1, 255), min(per_subnet, count - len(out))):
                out.append(str(ipaddress.IPv4Address(base + offset)))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"cursor": self.cursor, "laps": self.laps}), encoding="utf-8")
        except OSError:
            log.debug("could not save sweep cursor")
        return out


def _parse_line(line: str) -> Optional[tuple[str, Optional[int]]]:
    raw = line.strip()
    if not raw or raw.startswith(("#", ";", "//")):
        return None
    raw = raw.split("#", 1)[0].strip()
    for separator in (",", "\t", " ", "|", "@"):
        raw = raw.split(separator, 1)[0]
    raw = raw.strip("'\"[]() ").lower()
    host, sep, tail = raw.rpartition(":")
    if sep and tail.isdigit():
        port: Optional[int] = int(tail)
    else:
        host, port = raw, None
    if port is not None and not 0 < port < 65536:
        return None
    if any(item in host for item in _NOISE):
        return None
    if _IPV4.fullmatch(host):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None
    elif not _HOST.fullmatch(host):
        return None
    return host, port


async def fetch_list(url: str) -> list[tuple[str, Optional[int]]]:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"user-agent": f"{settings.brand}/2.0"})
        if response.status_code != 200:
            log.warning("source %s returned HTTP %s", url, response.status_code)
            return []
        body = response.text
        head = body[:768].lstrip().lower()
        if "html" in (response.headers.get("content-type") or "").lower() or any(x in head for x in _HTML):
            log.warning("source %s returned HTML, skipped", url)
            return []
    except Exception as error:  # noqa: BLE001
        log.warning("source %s failed: %s", url, error)
        return []
    out: list[tuple[str, Optional[int]]] = []
    seen: set[tuple[str, Optional[int]]] = set()
    for line in body.splitlines()[:5000]:
        item = _parse_line(line)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    log.info("source %s supplied %s candidates", url, len(out))
    return out


def read_local_list(path: str) -> list[tuple[str, Optional[int]]]:
    """Seed from a file on disk.

    The scheduled workflow commits a measured list to endpoints/clean-ips.txt.
    Reading it locally means a private repo works exactly as well as a public
    one, and a fresh deployment starts warm instead of blind.
    """
    target = Path(path)
    if not target.is_absolute():
        target = BASE_DIR / target
    try:
        body = target.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[tuple[str, Optional[int]]] = []
    seen: set[tuple[str, Optional[int]]] = set()
    for line in body.splitlines()[:5000]:
        item = _parse_line(line)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    if out:
        log.info("seed file %s supplied %s candidates", target, len(out))
    return out


async def resolve(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM),
            timeout=5,
        )
    except (OSError, asyncio.TimeoutError, socket.gaierror):
        return []
    return list(dict.fromkeys(item[4][0] for item in infos))


def _score(latency: float, jitter: float, kind: str) -> float:
    credit = 40 if kind == "domain" else 0
    return round(max(1, latency + jitter * 2.5 - credit), 1)


class CleanIPScanner:
    def __init__(self) -> None:
        self.ports = settings.all_ports
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._sweeper: Optional[SubnetSweeper] = None
        self._seeds: list[str] = []
        self._seeds_at = 0.0
        self._reference = ""
        self._reference_at = 0.0
        self.running = False
        self.last_run = 0
        self.last_found = 0
        self.waves = 0

    @property
    def sweeper(self) -> SubnetSweeper:
        if self._sweeper is None:
            self._sweeper = SubnetSweeper(settings.sweep_state)
        return self._sweeper

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="clean-ip-scanner-v2")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.scan_once(wait=False)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("clean-IP scan failed")
            # A little jitter so a fleet of bots never lines up on the same
            # minute, and so the sweep is not phase locked to the autopilot.
            delay = settings.scan_interval + random.randint(0, max(5, settings.scan_interval // 10))
            try:
                await asyncio.wait_for(self._stop.wait(), delay)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------ #
    # verification reference
    # ------------------------------------------------------------------ #

    async def reference_host(self) -> str:
        """A live panel hostname to point TLS probes at.

        Any Cloudflare edge address serves every workers.dev hostname, so one
        real panel is enough to prove an address and port will carry a
        WebSocket for all of them. VERIFY_HOST pins it manually; otherwise the
        newest successful deploy records itself here.
        """
        if not settings.verify_ws:
            return ""
        if settings.verify_host:
            return settings.verify_host
        if time.time() - self._reference_at < REFERENCE_TTL:
            return self._reference
        self._reference = (await db.get_option(REFERENCE_KEY, "")).strip().lower()
        self._reference_at = time.time()
        return self._reference

    async def _drop_reference(self, host: str) -> None:
        """Safety valve: a deleted panel must not be able to empty the pool."""
        if settings.verify_host:
            log.warning("VERIFY_HOST=%s verified nothing this sweep; check that panel is alive", host)
            return
        log.warning("reference panel %s verified nothing this sweep, dropping it", host)
        await db.set_option(REFERENCE_KEY, "")
        self._reference = ""
        self._reference_at = 0.0

    async def seeds(self) -> list[str]:
        age = time.time() - self._seeds_at
        if self._seeds and age < settings.source_ttl:
            return self._seeds
        if not self._seeds and age < settings.source_retry:
            return []
        found: list[str] = []
        candidates: list[tuple[str, Optional[int]]] = []
        for path in settings.clean_ip_files:
            candidates.extend(read_local_list(path))
        for url in settings.clean_ip_sources:
            candidates.extend(await fetch_list(url))
        for host, _ in candidates:
            if is_cloudflare(host):
                found.append(host)
            else:
                found.extend(ip for ip in await resolve(host) if is_cloudflare(ip))
        self._seeds = list(dict.fromkeys(found))[: settings.seed_limit]
        self._seeds_at = time.time()
        return self._seeds

    async def _current(self, port: int) -> list[tuple[str, str]]:
        rows = await db.fetch_all(
            "SELECT ip, kind FROM clean_ips WHERE port=? ORDER BY verified DESC, fails ASC, score ASC LIMIT ?",
            (port, settings.pool_size),
        )
        return [(str(row["ip"]), str(row["kind"] or "ip")) for row in rows]

    async def scan_once(self, batch: Optional[int] = None, wait: bool = True, wait_timeout: float = 90) -> int:
        if self._lock.locked():
            if not wait:
                return 0
            try:
                async with asyncio.timeout(wait_timeout):
                    async with self._lock:
                        pass
            except TimeoutError:
                pass
            return self.last_found
        async with self._lock:
            self.running = True
            self.waves = 0
            total = 0
            seeds = await self.seeds()
            reference = await self.reference_host()
            base = batch or settings.scan_batch
            sem = asyncio.Semaphore(settings.scan_concurrency)
            try:
                pending = list(self.ports)
                for wave in range(settings.scan_waves):
                    if not pending:
                        break
                    self.waves = wave + 1
                    results = await asyncio.gather(*[
                        self._scan_port(port, base * (wave + 1), seeds, wave, sem, reference)
                        for port in pending
                    ])
                    total += sum(results)
                    pending = [
                        port for port in pending
                        if len(await db.best_ips(port, settings.scan_min_verified)) < settings.scan_min_verified
                    ]
                if reference and total == 0:
                    await self._drop_reference(reference)
                await db.trim_pool(settings.pool_size)
                self.last_run = db.now()
                self.last_found = total
                await db.log_event(
                    "scan",
                    detail=(
                        f"stored={total} waves={self.waves} sweep={self.sweeper.progress}% "
                        f"lap={self.sweeper.laps + 1} check={'ws:' + reference if reference else 'trace'}"
                    ),
                )
                return total
            finally:
                self.running = False

    async def _scan_port(
        self,
        port: int,
        batch: int,
        seeds: list[str],
        wave: int,
        sem: asyncio.Semaphore,
        reference: str = "",
    ) -> int:
        candidates: list[tuple[str, str]] = []
        if wave == 0:
            candidates.extend((host, "domain") for host in settings.clean_domains)
            candidates.extend((ip, "ip") for ip in seeds)
            candidates.extend(await self._current(port))
        candidates.extend((ip, "ip") for ip in self.sweeper.take(batch, settings.sweep_per_subnet))
        unique = dict(candidates)

        async def knock(host: str, kind: str) -> Optional[dict]:
            async with sem:
                latency = await probe.connect_ms(host, port, settings.scan_timeout)
            if latency is None:
                await db.mark_ip_fail(host, port)
                return None
            return {"ip": host, "port": port, "kind": kind, "latency": latency}

        alive = [item for item in await asyncio.gather(*(knock(h, k) for h, k in unique.items())) if item]
        domains = [item for item in alive if item["kind"] == "domain"]
        raw = sorted((item for item in alive if item["kind"] != "domain"), key=lambda x: x["latency"])
        shortlist = domains + raw[: settings.verify_top]
        verify_sem = asyncio.Semaphore(max(8, min(32, settings.scan_concurrency // 4)))
        verified = await asyncio.gather(*(self._verify(item, verify_sem, reference) for item in shortlist))
        good = [item for item in verified if item]
        await db.store_clean_ips(good)
        log.info(
            "port %s wave %s: %s reachable, %s verified via %s",
            port, wave + 1, len(alive), len(good), "ws" if reference else "trace",
        )
        return len(good)

    async def _verify(self, item: dict, sem: asyncio.Semaphore, reference: str = "") -> Optional[dict]:
        """Prove one address on one port, the way a client will use it.

        With a reference hostname this is a full TLS-with-real-SNI plus
        WebSocket upgrade, and a ``101`` is the only acceptable answer. Without
        one, the weaker trace check warms a cold pool. There is deliberately no
        fallback from the first to the second: falling back is what let port 443
        fill up with addresses no client could use.
        """
        port = int(item["port"])
        tls = port in settings.tls_ports
        async with sem:
            result = await probe.measure(
                item["ip"],
                port,
                tls=tls,
                host=reference or None,
                path=WS_PATH,
                rounds=settings.scan_rounds,
                timeout=settings.scan_timeout * 3,
            )
        if result is None:
            await db.mark_ip_fail(item["ip"], port)
            return None
        return {
            **item,
            "latency": result["latency"],
            "jitter": result["jitter"],
            "score": _score(result["latency"], result["jitter"], item["kind"]),
            "colo": result["colo"],
            "verified": True,
        }

    async def pick(self, port: int, count: int, verified_only: bool = True) -> list[dict]:
        clause = "AND verified=1" if verified_only else ""
        rows = await db.fetch_all(
            f"SELECT ip,port,latency,jitter,score,kind,colo,verified,checked_at FROM clean_ips "
            f"WHERE port=? AND fails < ? {clause} ORDER BY (checked_at >= ?) DESC, score ASC, latency ASC LIMIT ?",
            (port, settings.max_fails, db.now() - settings.scan_ttl, max(24, count * 10)),
        )
        out: list[dict] = []
        subnets: set[str] = set()
        for row in rows:
            key = _subnet_key(str(row["ip"]))
            if key in subnets:
                continue
            subnets.add(key)
            out.append(dict(row))
            if len(out) >= count:
                return out
        for row in rows:
            item = dict(row)
            if item not in out:
                out.append(item)
            if len(out) >= count:
                break
        return out

    async def demote(self, ip: str, port: int) -> None:
        await db.mark_ip_fail(ip, port)

    async def stats(self) -> dict:
        data = await db.pool_stats()
        data.update({
            "scanning": self.running,
            "last_run": self.last_run,
            "ports": list(self.ports),
            "coverage": await db.port_coverage(),
            "sweep": self.sweeper.progress,
            "laps": self.sweeper.laps,
            "reference": await self.reference_host(),
        })
        return data


class ProxyIPScanner:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self.running = False
        self.last_run = 0
        self.last_found = 0

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="proxy-scanner-v2")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.scan_once(wait=False)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("proxy scan failed")
            try:
                await asyncio.wait_for(self._stop.wait(), settings.proxy_scan_interval)
            except asyncio.TimeoutError:
                pass

    async def candidates(self) -> list[tuple[str, int]]:
        default = settings.proxy_ports[0] if settings.proxy_ports else 443
        out: list[tuple[str, int]] = []
        for raw in settings.proxy_seeds:
            host, sep, tail = raw.strip().lower().rpartition(":")
            out.append((host if sep and tail.isdigit() else raw.strip().lower(), int(tail) if sep and tail.isdigit() else default))
        for url in settings.proxy_sources:
            out.extend((host, port or default) for host, port in await fetch_list(url))
        out.extend((str(row["host"]), int(row["port"])) for row in await proxies.best(settings.proxy_pool_size, verified_only=False))
        return list(dict.fromkeys(out))[: settings.proxy_scan_limit]

    async def scan_once(self, wait: bool = True, wait_timeout: float = 90) -> int:
        if self._lock.locked():
            if wait:
                try:
                    async with asyncio.timeout(wait_timeout):
                        async with self._lock:
                            pass
                except TimeoutError:
                    pass
            return self.last_found
        async with self._lock:
            self.running = True
            try:
                sem = asyncio.Semaphore(min(64, settings.scan_concurrency))
                results = await asyncio.gather(*(self._verify(h, p, sem) for h, p in await self.candidates()))
                good = [item for item in results if item]
                await proxies.store(good)
                await proxies.trim(settings.proxy_pool_size * 2)
                self.last_found = len(good)
                self.last_run = db.now()
                return len(good)
            finally:
                self.running = False

    async def _verify(self, host: str, port: int, sem: asyncio.Semaphore) -> Optional[dict]:
        async with sem:
            addresses = await resolve(host)
            if not addresses or all(is_cloudflare(item) for item in addresses):
                return None
            samples = [await probe.connect_ms(host, port, 6) for _ in range(2)]
            samples = [item for item in samples if item is not None]
            if len(samples) < 2:
                return None
            # A relay is not a worker: there is no WebSocket to upgrade here, so
            # the trace check is the right one and the strongest available.
            result = await probe.trace(host, port, True, 7)
        if result is None:
            return None
        return {"host": host, "port": port, "latency": round(statistics.median(samples), 1), "colo": result["colo"], "verified": True}

    async def pick(self, count: int) -> list[dict]:
        rows = await proxies.best(count, verified_only=True)
        return rows or await proxies.best(count, verified_only=False)

    async def stats(self) -> dict:
        data = await proxies.stats()
        data.update({"scanning": self.running, "last_run": self.last_run})
        return data


scanner = CleanIPScanner()
proxy_scanner = ProxyIPScanner()
