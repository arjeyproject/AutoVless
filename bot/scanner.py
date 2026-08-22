"""Clean IP and proxyIP scanners.

Two independent background jobs, both tuned for a 1 vCPU / 1 GB box:

  CleanIPScanner   entry points the client dials. Curated seed lists, the
                   addresses already in the pool, and a rotating sweep that
                   walks every Cloudflare /24 in a fixed shuffled order, so
                   coverage is exhaustive over time instead of a lottery.
                   Survivors are timed over several real handshakes and then
                   verified with a request to /cdn-cgi/trace, which also
                   reveals the edge colo.

  ProxyIPScanner   relays the worker uses to reach hosts that sit behind
                   Cloudflare. A Worker cannot open a socket to a
                   Cloudflare-owned address, so anything resolving into a
                   Cloudflare prefix is rejected outright.

Every number stored here is measured. Nothing is estimated, scaled or
borrowed from a neighbouring probe.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import random
import re
import socket
import ssl
import statistics
import time
from pathlib import Path
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
TRACE_PATH = "/cdn-cgi/trace"

_NETWORKS = [ipaddress.ip_network(prefix) for prefix in CF_PREFIXES]
_WEIGHTS = [net.num_addresses for net in _NETWORKS]

# The /24 order is shuffled once with a fixed seed. Same order on every boot,
# which is what makes a saved cursor mean anything.
SWEEP_SEED = 0x0CF24

_HTML_MARKERS = (
    "<!doctype",
    "<html",
    "<head",
    "<body",
    "<script",
    "<div",
    "<span",
    "<meta",
)

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_HOSTNAME = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
_SOURCE_NOISE = (
    "github.com",
    "githubusercontent.com",
    "t.me",
    "telegram.org",
    "cloudflare.com",
    "example.com",
    "030101.xyz",
)


def is_cloudflare(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in net for net in _NETWORKS)


def random_ips(count: int) -> list[str]:
    """Sample addresses across Cloudflare prefixes, weighted by prefix size.

    Kept for one-off probes. The background sweep uses SubnetSweeper instead,
    because a weighted lottery over a /13 revisits nothing and covers nothing.
    """
    picked: set[str] = set()
    guard = 0
    while len(picked) < count and guard < count * 8:
        guard += 1
        net = random.choices(_NETWORKS, weights=_WEIGHTS, k=1)[0]
        offset = random.randint(1, max(1, net.num_addresses - 2))
        picked.add(str(net.network_address + offset))
    return list(picked)


# ===================================================================== #
# rotating /24 sweep
# ===================================================================== #


def _all_subnets() -> list[int]:
    out: list[int] = []
    for net in _NETWORKS:
        for subnet in net.subnets(new_prefix=24):
            out.append(int(subnet.network_address))
    random.Random(SWEEP_SEED).shuffle(out)
    return out


class SubnetSweeper:
    """Hands out addresses from one /24 after another, and never forgets where
    it stopped.

    Cloudflare hands out edges per /24, so one live answer inside a block says
    a lot about the block. Walking them in a fixed order means every corner of
    the network is reached within a known number of sweeps, and the cursor is
    persisted so a restart continues instead of rolling the dice again.
    """

    def __init__(self, state_file: Path) -> None:
        self._subnets = _all_subnets()
        self._state_file = state_file
        self.cursor = 0
        self.laps = 0
        self._load()

    # ---------------------------------------------------------------- state

    def _load(self) -> None:
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            self.cursor = int(raw.get("cursor", 0)) % len(self._subnets)
            self.laps = int(raw.get("laps", 0))
        except (OSError, ValueError, TypeError, ZeroDivisionError):
            self.cursor = 0
            self.laps = 0

    def save(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"cursor": self.cursor, "laps": self.laps}),
                encoding="utf-8",
            )
        except OSError:
            log.debug("could not persist sweep cursor")

    # ---------------------------------------------------------------- reads

    @property
    def total(self) -> int:
        return len(self._subnets)

    @property
    def progress(self) -> float:
        """How far through the current lap, as a percentage."""
        if not self._subnets:
            return 0.0
        return round(self.cursor / len(self._subnets) * 100, 1)

    # ---------------------------------------------------------------- take

    def take(self, count: int, per_subnet: int = 2) -> list[str]:
        if count <= 0 or not self._subnets:
            return []
        per_subnet = max(1, per_subnet)
        picked: list[str] = []
        blocks = min(len(self._subnets), max(1, count // per_subnet))

        for _ in range(blocks):
            base = self._subnets[self.cursor]
            self.cursor += 1
            if self.cursor >= len(self._subnets):
                self.cursor = 0
                self.laps += 1
                log.info("sweep completed lap %s over %s /24s", self.laps, len(self._subnets))
            offsets = random.sample(range(1, 255), per_subnet)
            for offset in offsets:
                picked.append(str(ipaddress.IPv4Address(base + offset)))

        self.save()
        return picked[:count]


# ===================================================================== #
# source lists
# ===================================================================== #


def _split_entry(line: str) -> Optional[tuple[str, Optional[int]]]:
    """Pull one host (and port, if present) out of a single list line."""
    raw = line.strip()
    if not raw or raw[0] in "#;" or raw.startswith("//"):
        return None
    raw = raw.split("#", 1)[0]
    for separator in (",", "\t", " ", "|", "@"):
        if separator in raw:
            raw = raw.split(separator, 1)[0]
    raw = raw.strip().strip("'\"[]()").lower()
    if not raw:
        return None

    host, _, tail = raw.rpartition(":")
    if host and tail.isdigit():
        port: Optional[int] = int(tail)
    else:
        host, port = raw, None

    if not (_IPV4.match(host) or _HOSTNAME.match(host)):
        return None
    if any(noise in host for noise in _SOURCE_NOISE):
        return None
    if _IPV4.match(host):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None
    if port is not None and not (0 < port < 65536):
        return None
    return host, port


async def fetch_list(url: str) -> list[tuple[str, Optional[int]]]:
    """Pull a community list and parse it line by line.

    Public list endpoints rot. They start returning a landing page, a rate
    limit notice or a login wall, all with HTTP 200, and a scraper that shrugs
    and returns an empty list makes that look like "no clean IPs today"
    forever. So anything that smells like markup is rejected out loud.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": f"{settings.brand}/1.0"})
        if response.status_code != 200:
            log.warning("source %s answered HTTP %s", url, response.status_code)
            return []
        content_type = (response.headers.get("content-type") or "").lower()
        body = response.text
    except Exception:  # noqa: BLE001
        log.warning("source unreachable: %s", url)
        return []

    head = body[:512].lstrip().lower()
    if "html" in content_type or any(marker in head for marker in _HTML_MARKERS):
        log.warning("source %s is serving a web page, not a list. skipping it", url)
        return []

    found: list[tuple[str, Optional[int]]] = []
    seen: set[str] = set()
    for line in body.splitlines()[:4000]:
        entry = _split_entry(line)
        if entry is None or entry[0] in seen:
            continue
        seen.add(entry[0])
        found.append(entry)

    if not found:
        log.warning("source %s parsed to zero usable hosts", url)
    else:
        log.info("source %s gave %s hosts", url, len(found))
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


# ===================================================================== #
# probes
# ===================================================================== #


async def _close(writer: Optional[asyncio.StreamWriter]) -> None:
    if writer is None:
        return
    writer.close()
    try:
        await writer.wait_closed()
    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        pass


async def _connect_once(host: str, port: int, timeout: float) -> Optional[float]:
    """One TCP handshake. Returns the round trip in ms, or None."""
    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, asyncio.TimeoutError, ssl.SSLError, ValueError):
        return None
    elapsed = (time.perf_counter() - start) * 1000
    await _close(writer)
    return elapsed


async def measure(host: str, port: int, rounds: int, timeout: float) -> Optional[dict]:
    """Time several handshakes and report the median, jitter and loss.

    A single connect is noise. An address that answers once and then stalls is
    worse than one that never answered, because it ends up in somebody's
    config. So a candidate has to answer at least twice.
    """
    rounds = max(2, rounds)
    samples: list[float] = []
    for index in range(rounds):
        if index:
            await asyncio.sleep(0.12)
        value = await _connect_once(host, port, timeout)
        if value is not None:
            samples.append(value)

    if len(samples) < max(2, rounds - 1):
        return None
    return {
        "latency": round(statistics.median(samples), 1),
        "jitter": round(max(samples) - min(samples), 1),
        "loss": round((rounds - len(samples)) / rounds, 2),
    }


async def _read_head(reader: asyncio.StreamReader, timeout: float, limit: int = 8192) -> bytes:
    """Read until the response headers are complete, not just once."""
    buffer = b""
    while len(buffer) < limit:
        try:
            chunk = await asyncio.wait_for(reader.read(2048), timeout=timeout)
        except (OSError, asyncio.TimeoutError, ssl.SSLError):
            break
        if not chunk:
            break
        buffer += chunk
        if b"\r\n\r\n" in buffer:
            break
    return buffer


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
            f"GET {TRACE_PATH} HTTP/1.1\r\n"
            f"Host: {sni}\r\n"
            f"User-Agent: {settings.brand}/1.0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(request)
        await writer.drain()
        raw = await _read_head(reader, timeout)
    except (OSError, asyncio.TimeoutError, ssl.SSLError, ValueError):
        return None
    finally:
        await _close(writer)

    text = raw.decode("latin-1", errors="ignore")
    if not text or not _ok_status(text):
        return None
    colo = _extract_colo(text)
    if colo is None:
        return None
    return {"latency": round((time.perf_counter() - start) * 1000, 1), "colo": colo}


# ===================================================================== #
# clean entry points
# ===================================================================== #


class CleanIPScanner:
    def __init__(self) -> None:
        self.ports: tuple[int, ...] = tuple(dict.fromkeys(settings.tls_ports + settings.http_ports))
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._sweeper: Optional[SubnetSweeper] = None
        self._seeds: list[str] = []
        self._seeds_at: float = 0.0
        self._schema_ready = False
        self.last_run: int = 0
        self.last_found: int = 0
        self.running: bool = False

    # ------------------------------------------------------------------ #
    # storage
    # ------------------------------------------------------------------ #

    async def ensure_schema(self) -> None:
        """The pool table lives in db.SCHEMA; jitter and loss were added later."""
        if self._schema_ready:
            return
        async with db.conn().execute("PRAGMA table_info(clean_ips)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        for column in ("jitter", "loss"):
            if column not in columns:
                await db.conn().execute(
                    f"ALTER TABLE clean_ips ADD COLUMN {column} REAL NOT NULL DEFAULT 0"
                )
        await db.conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_clean_fresh ON clean_ips (port, verified, checked_at)"
        )
        await db.conn().commit()
        self._schema_ready = True

    async def store(self, rows: list[dict]) -> None:
        if not rows:
            return
        await self.ensure_schema()
        ts = db.now()
        payload = [
            (
                row["ip"],
                int(row["port"]),
                float(row["latency"]),
                float(row.get("jitter") or 0),
                float(row.get("loss") or 0),
                row.get("colo"),
                1 if row.get("verified") else 0,
                ts,
            )
            for row in rows
        ]
        await db.conn().executemany(
            "INSERT INTO clean_ips (ip, port, latency, jitter, loss, colo, verified, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(ip, port) DO UPDATE SET "
            "latency = excluded.latency, jitter = excluded.jitter, loss = excluded.loss, "
            "colo = COALESCE(excluded.colo, clean_ips.colo), "
            "verified = excluded.verified, checked_at = excluded.checked_at",
            payload,
        )
        await db.conn().commit()

    async def trim(self) -> None:
        """Keep the pool per port, and rank freshness above raw latency.

        Trimming the table as a whole was quietly fatal: a plain HTTP handshake
        always finishes sooner than a TLS one, so port 80 rows won every
        comparison and port 443 was evicted out of existence within a few
        sweeps. Sorting fresh rows first is what stops the pool from fossilising
        around whatever got lucky on the very first sweep.
        """
        await self.ensure_schema()
        fresh_after = db.now() - settings.scan_ttl
        await db.execute(
            "DELETE FROM clean_ips WHERE rowid NOT IN ("
            "  SELECT rowid FROM ("
            "    SELECT rowid, ROW_NUMBER() OVER ("
            "      PARTITION BY port"
            "      ORDER BY verified DESC, (checked_at >= ?) DESC, latency ASC"
            "    ) AS position FROM clean_ips"
            "  ) WHERE position <= ?"
            ")",
            (fresh_after, settings.pool_size),
        )
        await db.execute(
            "DELETE FROM clean_ips WHERE checked_at < ?",
            (db.now() - settings.scan_ttl * settings.stale_factor,),
        )

    async def fresh_keys(self) -> set[str]:
        """"ip:port" of every endpoint verified inside the freshness window."""
        await self.ensure_schema()
        rows = await db.fetch_all(
            "SELECT ip, port FROM clean_ips WHERE verified = 1 AND checked_at >= ?",
            (db.now() - settings.scan_ttl,),
        )
        return {f"{row['ip']}:{row['port']}" for row in rows}

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    @property
    def sweeper(self) -> SubnetSweeper:
        if self._sweeper is None:
            self._sweeper = SubnetSweeper(settings.sweep_state)
            log.info(
                "sweep ready: %s /24 blocks, resuming at %s%% of lap %s",
                self._sweeper.total,
                self._sweeper.progress,
                self._sweeper.laps + 1,
            )
        return self._sweeper

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
                await self.scan_once(wait=False)
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

    async def seeds(self) -> list[str]:
        """Curated addresses from public lists.

        A sweep alone mostly finds edges on the other side of the planet.
        Seeding with known-good addresses is what makes the first build usable
        instead of merely reachable. A successful fetch is cached for an hour;
        a failed one is retried much sooner, because caching an empty list for
        an hour is how a dead source turns into a dead scanner.
        """
        age = time.time() - self._seeds_at
        if self._seeds and age < settings.source_ttl:
            return self._seeds
        if not self._seeds and age < settings.source_retry:
            return []

        found: list[str] = []
        for url in settings.clean_ip_sources:
            for host, _port in await fetch_list(url):
                if is_cloudflare(host):
                    found.append(host)
                    continue
                for address in await resolve(host):
                    if is_cloudflare(address):
                        found.append(address)

        self._seeds = list(dict.fromkeys(found))[: settings.seed_limit]
        self._seeds_at = time.time()
        if self._seeds:
            log.info("loaded %s seed addresses", len(self._seeds))
        else:
            log.warning(
                "every clean IP source came back empty, running on the sweep alone. "
                "check CLEAN_IP_SOURCES"
            )
        return self._seeds

    async def candidates(self, port: int, batch: int, seeds: list[str]) -> list[str]:
        """Seeds, the current pool, and the next slice of the sweep.

        Re-probing what is already in the pool matters as much as finding new
        addresses: it is the only way an entry that has gone bad gets demoted,
        and the only way a good one keeps a fresh timestamp.
        """
        pool = [
            row["ip"]
            for row in await db.fetch_all(
                "SELECT ip FROM clean_ips WHERE port = ? ORDER BY latency ASC LIMIT ?",
                (port, settings.pool_size),
            )
        ]
        sweep = self.sweeper.take(batch, settings.sweep_per_subnet)
        return list(dict.fromkeys(seeds + pool + sweep))

    async def scan_once(
        self,
        batch: Optional[int] = None,
        wait: bool = True,
        wait_timeout: float = 45.0,
    ) -> int:
        """Run one full sweep. Returns the number of verified endpoints stored.

        When a sweep is already running the caller used to get 0, which read as
        "found nothing" everywhere in the UI. Now it waits for the sweep in
        flight and reports what that one actually found.
        """
        if self._lock.locked():
            if not wait:
                return 0
            try:
                await asyncio.wait_for(self._wait_idle(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                log.info("a sweep is still running; reporting the last completed one")
            return self.last_found

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            batch = batch or settings.scan_batch
            await self.ensure_schema()
            semaphore = asyncio.Semaphore(settings.scan_concurrency)
            seeds = await self.seeds()
            stored = 0

            try:
                for port in self.ports:
                    candidates = await self.candidates(port, batch, seeds)
                    reachable = await asyncio.gather(
                        *(self._knock(ip, port, semaphore) for ip in candidates)
                    )
                    alive = sorted((r for r in reachable if r), key=lambda r: r["latency"])
                    shortlist = alive[: settings.verify_top]

                    # TLS ports answer less often, so give them a second slice
                    # of the sweep rather than shipping an empty port 443.
                    if len(shortlist) < 4 and port in settings.tls_ports:
                        log.info("port %s light on answers (%s), extending the sweep", port, len(alive))
                        extra = self.sweeper.take(batch * 2, settings.sweep_per_subnet)
                        more = await asyncio.gather(
                            *(self._knock(ip, port, semaphore) for ip in extra)
                        )
                        alive.extend(r for r in more if r)
                        alive.sort(key=lambda r: r["latency"])
                        shortlist = alive[: settings.verify_top]

                    verify_semaphore = asyncio.Semaphore(min(24, settings.scan_concurrency))
                    verified = await asyncio.gather(
                        *(self._verify(item, verify_semaphore) for item in shortlist)
                    )
                    good = [v for v in verified if v]
                    await self.store(good)
                    stored += len(good)
                    log.info(
                        "port %s: %s of %s answered, %s verified",
                        port,
                        len(alive),
                        len(candidates),
                        len(good),
                    )

                await self.trim()
                self.last_run = db.now()
                self.last_found = stored
                await db.log_event(
                    "scan",
                    detail=(
                        f"stored={stored} sweep={self.sweeper.progress}% "
                        f"lap={self.sweeper.laps + 1} "
                        f"elapsed={time.perf_counter() - started:.1f}s"
                    ),
                )
                return stored
            finally:
                self.running = False

    async def _wait_idle(self) -> None:
        async with self._lock:
            return

    async def _knock(self, ip: str, port: int, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """Cheap first pass: one handshake, only to decide who gets timed properly."""
        async with semaphore:
            latency = await _connect_once(ip, port, settings.scan_timeout)
        if latency is None:
            return None
        return {"ip": ip, "port": port, "latency": latency}

    async def _verify(self, candidate: dict, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """Time the address properly, then prove it really is a Cloudflare edge.

        The stored latency is the median of real handshakes. The old code shipped
        min(trace_latency, first_connect * 6), a number that never corresponded
        to anything measurable, and it was the number users saw in their config
        names.
        """
        ip, port = candidate["ip"], int(candidate["port"])
        use_tls = port in settings.tls_ports

        async with semaphore:
            timing = await measure(ip, port, settings.scan_rounds, settings.scan_timeout * 2)
            if timing is None:
                return None
            trace = await trace_probe(ip, port, use_tls, settings.scan_timeout * 3)

        if trace is None:
            return None
        return {
            "ip": ip,
            "port": port,
            "latency": timing["latency"],
            "jitter": timing["jitter"],
            "loss": timing["loss"],
            "colo": trace["colo"],
            "verified": True,
        }

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    async def stats(self) -> dict:
        pool = await db.pool_stats()
        await self.ensure_schema()
        pool["fresh"] = int(
            await db.scalar(
                "SELECT COUNT(*) FROM clean_ips WHERE verified = 1 AND checked_at >= ?",
                (db.now() - settings.scan_ttl,),
            )
        )
        pool["by_port"] = {
            int(row["port"]): int(row["live"])
            for row in await db.fetch_all(
                "SELECT port, COUNT(*) AS live FROM clean_ips WHERE verified = 1 GROUP BY port"
            )
        }
        pool["scanning"] = self.running
        pool["last_run"] = self.last_run
        pool["ports"] = list(self.ports)
        pool["sweep"] = self.sweeper.progress
        pool["laps"] = self.sweeper.laps
        pool["blocks"] = self.sweeper.total
        return pool

    async def pick(self, port: int, count: int) -> list[dict]:
        """Best endpoints for a port: fresh and verified first, then older, then
        whatever answered at all. Never an empty list while the pool has rows.
        """
        await self.ensure_schema()
        picked: list[dict] = []
        seen: set[str] = set()

        tiers = (
            ("verified = 1 AND checked_at >= ?", (db.now() - settings.scan_ttl,)),
            ("verified = 1", ()),
            ("1 = 1", ()),
        )
        for clause, params in tiers:
            if len(picked) >= count:
                break
            rows = await db.fetch_all(
                f"SELECT ip, port, latency, jitter, colo FROM clean_ips "
                f"WHERE port = ? AND {clause} ORDER BY latency ASC LIMIT ?",
                (port, *params, count * 3),
            )
            for row in rows:
                if row["ip"] in seen:
                    continue
                seen.add(row["ip"])
                picked.append(dict(row))
                if len(picked) >= count:
                    break
        return picked[:count]


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
        self.last_found: int = 0

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
                await self.scan_once(wait=False)
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

    async def scan_once(self, wait: bool = True, wait_timeout: float = 45.0) -> int:
        if self._lock.locked():
            if not wait:
                return 0
            try:
                await asyncio.wait_for(self._wait_idle(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                log.info("a relay sweep is still running; reporting the last completed one")
            return self.last_found

        async with self._lock:
            self.running = True
            started = time.perf_counter()
            try:
                candidates = await self.candidates()
                if not candidates:
                    log.warning("no relay candidates at all. check PROXY_IP_SOURCES")
                    return 0

                semaphore = asyncio.Semaphore(min(48, settings.scan_concurrency))
                results = await asyncio.gather(
                    *(self._verify(host, port, semaphore) for host, port in candidates)
                )
                good = [r for r in results if r]
                await proxies.store(good)
                await proxies.trim(settings.proxy_pool_size * 2)
                self.last_run = db.now()
                self.last_found = len(good)
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

    async def _wait_idle(self) -> None:
        async with self._lock:
            return

    async def _verify(self, host: str, port: int, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """A usable relay forwards TCP to the Cloudflare edge and is not itself
        a Cloudflare address, because Workers cannot dial those."""
        async with semaphore:
            addresses = await resolve(host)
            if not addresses:
                return None
            if all(is_cloudflare(address) for address in addresses):
                return None

            timing = await measure(host, port, settings.scan_rounds, 6.0)
            if timing is None:
                return None
            result = await trace_probe(host, port, use_tls=True, timeout=6.0)

        if result is None:
            return None
        return {
            "host": host,
            "port": port,
            "latency": timing["latency"],
            "colo": result["colo"],
            "verified": True,
        }

    async def pick(self, count: int) -> list[dict]:
        rows = await proxies.best(count, verified_only=True)
        if not rows:
            rows = await proxies.best(count, verified_only=False)
        return rows[:count]

    async def stats(self) -> dict:
        data = await proxies.stats()
        data["scanning"] = self.running
        data["last_run"] = self.last_run
        return data


scanner = CleanIPScanner()
proxy_scanner = ProxyIPScanner()
