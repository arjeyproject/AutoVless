"""Build and refresh Cloudflare panels with explicit health and publish gates.

Server-side checks do not establish connectivity on every client network.
A failed worker health check must not demote the shared clean-IP pool, and the
subscription must receive the final accepted addresses before reporting success.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import httpx

from . import db, proxies, vless
from .cloudflare import CloudflareClient, CloudflareError, script_name
from .config import settings
from .probe import measure
from .scanner import proxy_scanner, scanner

log = logging.getLogger("autovless.deploy")
STEP_KEYS: tuple[str, ...] = (
    "step_verify", "step_subdomain", "step_scan", "step_deploy", "step_health",
)
MARK_DONE = "\u2705"
MARK_ACTIVE = "\u23f3"
MARK_IDLE = "\u25ab\ufe0f"
ACCEPT_ROUNDS = 3
ACCEPT_REQUIRED = 2
Progress = Optional[Callable[[int], Awaitable[None]]]


class DeployError(Exception):
    def __init__(self, reason: object) -> None:
        super().__init__(str(reason))
        self.reason = str(reason)


@dataclass
class Panel:
    account_id: str
    script: str
    host: str
    uuid: str
    endpoints: list[dict] = field(default_factory=list)
    relays: list[str] = field(default_factory=list)
    build_ms: int = 0
    healthy: bool = False
    probe: dict = field(default_factory=dict)
    rejected: int = 0


def render_steps(lang: str, index: int, translate) -> str:
    lines = []
    for position, key in enumerate(STEP_KEYS):
        if position < index:
            mark = MARK_DONE
        elif position == index:
            mark = MARK_ACTIVE
        else:
            mark = MARK_IDLE
        lines.append(f"{mark} {translate(lang, key)}")
    return "\n".join(lines)


async def _announce(progress: Progress, index: int) -> None:
    if progress is None:
        return
    try:
        await progress(index)
    except Exception:
        log.debug("progress update failed")


async def _select_endpoints(force_scan: bool) -> list[dict]:
    pool = await db.pool_stats()
    if force_scan or pool["verified"] < settings.config_count:
        await scanner.scan_once()
    endpoints = await vless.collect_endpoints(scanner)
    if len(endpoints) < settings.config_count:
        await scanner.scan_once()
        endpoints = await vless.collect_endpoints(scanner)
    if not endpoints:
        raise DeployError("clean ip pool is empty")
    return endpoints


async def _select_relays() -> list[str]:
    rows = await proxy_scanner.pick(settings.proxy_per_panel)
    if not rows:
        await proxy_scanner.scan_once()
        rows = await proxy_scanner.pick(settings.proxy_per_panel)
    relays = [
        f"{row['host']}:{int(row['port'])}" if int(row["port"]) != 443 else str(row["host"])
        for row in rows
    ]
    for seed in settings.proxy_seeds:
        if len(relays) >= settings.proxy_per_panel + 2:
            break
        if seed not in relays:
            relays.append(seed)
    return relays[: settings.proxy_per_panel + 2]


def _bindings(uuid: str, host: str, endpoints: list[dict], relays: list[str]) -> dict[str, str]:
    return {
        "UUID": uuid, "PROXY_IP": ",".join(relays), "SUB_HOST": host,
        "BRAND": settings.brand, "WS_PATH": vless.WS_PATH,
        "ENDPOINTS": json.dumps(endpoints, ensure_ascii=False),
        "SUB_SOURCES": ",".join(settings.sub_sources),
        "CLEAN_DOMAINS": ",".join(settings.clean_domains),
        "SUB_REFRESH": str(settings.sub_refresh),
        "TLS_PORTS": ",".join(str(p) for p in settings.tls_ports),
        "HTTP_PORTS": ",".join(str(p) for p in settings.http_ports),
        "TLS_COUNT": str(settings.tls_config_count), "HTTP_COUNT": str(settings.http_config_count),
        "DNS_SERVER": settings.dns_server, "FALLBACK_HOST": settings.fallback_host,
        "BUILD_ID": str(int(time.time())),
    }


async def _accept(host: str, endpoints: list[dict]) -> tuple[list[dict], list[dict]]:
    keep: list[dict] = []
    dead: list[dict] = []
    for endpoint in endpoints:
        port = int(endpoint["port"])
        result = await measure(
            str(endpoint["ip"]), port, tls=vless.is_tls(port), host=host,
            path=vless.WS_PATH, rounds=ACCEPT_ROUNDS, required=ACCEPT_REQUIRED,
            timeout=settings.accept_timeout,
        )
        if result is None:
            log.info("rejected %s:%s for %s, no websocket upgrade", endpoint["ip"], port, host)
            await scanner.demote(str(endpoint["ip"]), port)
            dead.append(endpoint)
            continue
        keep.append({
            **endpoint, "latency": result["latency"], "jitter": result["jitter"],
            "colo": result["colo"], "verified": True,
        })
    return keep, dead


async def _ship(host: str, endpoints: list[dict]) -> tuple[list[dict], list[dict]]:
    """Accept, then replace failed entries within the same TLS/HTTP group."""
    keep, dead = await _accept(host, endpoints)
    if not dead:
        return keep, []
    seen = {str(item["ip"]) for item in keep} | {str(item["ip"]) for item in dead}
    for attempt in range(max(0, settings.accept_retries)):
        missing_tls = sum(1 for item in dead if vless.is_tls(item["port"]))
        missing_http = len(dead) - missing_tls
        if not dead:
            break
        candidates: list[dict] = []
        if missing_tls:
            candidates += await vless.spare_endpoints(scanner, settings.tls_ports, missing_tls * 3, seen)
        if missing_http:
            candidates += await vless.spare_endpoints(scanner, settings.http_ports, missing_http * 3, seen)
        if not candidates:
            if attempt == 0:
                await scanner.scan_once()
                continue
            break
        seen |= {str(item["ip"]) for item in candidates}
        fresh, _ = await _accept(host, candidates)
        if not fresh:
            continue
        healed: list[dict] = []
        for item in dead:
            group = vless.group_of(item["port"])
            match = next((row for row in fresh if vless.group_of(row["port"]) == group), None)
            if match is None:
                continue
            fresh.remove(match)
            keep.append(match)
            healed.append(item)
        dead = [item for item in dead if item not in healed]
        if not dead:
            break
    if dead:
        log.warning(
            "shipping %s endpoints, %s could not be replaced: %s", len(keep), len(dead),
            ", ".join(f"{item['ip']}:{item['port']}" for item in dead),
        )
    return keep, dead


def _endpoint_keys(endpoints: list[dict]) -> list[tuple[str, int]]:
    return [(str(row["ip"]), int(row["port"])) for row in endpoints]


def _require_healthy(healthy: bool, report: dict) -> None:
    if not healthy:
        reason = report.get("reason") or "outbound probe did not pass"
        raise DeployError(
            f"panel health check failed: {reason}; check Cloudflare Workers logs, "
            "account status and limits before retrying"
        )


async def _health(host: str, uuid: str, attempts: Optional[int] = None) -> tuple[bool, dict]:
    """Validate both response shapes; never mistake a failed worker for bad IPs."""
    health_url = f"https://{host}/{uuid}/health"
    probe_url = f"https://{host}/{uuid}/probe"
    tries = attempts or settings.health_attempts
    report = {"reason": "health endpoint did not respond"}
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
        live = False
        for attempt in range(tries):
            try:
                response = await client.get(health_url)
                report = {"reason": f"health endpoint HTTP {response.status_code}"}
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("ok") is True:
                        live = True
                        break
                    report = {"reason": "invalid health response"}
                if response.status_code in (401, 403, 429):
                    break
            except (httpx.HTTPError, ValueError):
                report = {"reason": "health request failed or returned invalid JSON"}
            if attempt + 1 < tries:
                await asyncio.sleep(min(2 + attempt * 2, 8))
        if not live:
            return False, report
        try:
            response = await client.get(probe_url)
            if response.status_code != 200:
                return False, {"reason": f"outbound probe HTTP {response.status_code}"}
            report = response.json()
            if not isinstance(report, dict):
                return False, {"reason": "invalid outbound probe response"}
        except (httpx.HTTPError, ValueError):
            return False, {"reason": "outbound probe request failed or returned invalid JSON"}
    return report.get("ok") is True, report


async def _demote_dead_relays(report: dict) -> None:
    for relay in report.get("relays") or []:
        if relay.get("ok"):
            continue
        target = str(relay.get("target") or "")
        host, _, port = target.partition(":")
        if host:
            await proxies.mark_fail(host, int(port) if port.isdigit() else 443)


async def _remember_reference(host: str) -> None:
    try:
        await db.set_option("verify_host", host.lower())
    except Exception:
        log.debug("could not record verification host")


def _read_worker() -> str:
    try:
        return settings.worker_file.read_text(encoding="utf-8")
    except OSError as error:
        raise DeployError(f"worker bundle unreadable: {error}") from error


async def build(
    token: str,
    reuse: Optional[dict] = None,
    progress: Progress = None,
    force_scan: bool = False,
) -> Panel:
    started = time.perf_counter()
    reuse = reuse or {}
    code = _read_worker()
    await _announce(progress, 0)
    try:
        async with CloudflareClient(token) as cf:
            await cf.verify_token()
            account_id = reuse.get("account_id") or str((await cf.first_account())["id"])
            await _announce(progress, 1)
            subdomain = await cf.ensure_subdomain(account_id)
            if not subdomain:
                raise DeployError(
                    "the token cannot reserve a workers.dev subdomain; "
                    "add the Workers Scripts: Edit permission"
                )
            await _announce(progress, 2)
            endpoints = await _select_endpoints(force_scan)
            relays = await _select_relays()
            script = reuse.get("script_name") or script_name()
            panel_uuid = reuse.get("uuid") or vless.new_uuid()
            host = f"{script}.{subdomain}.workers.dev"
            await _announce(progress, 3)
            await cf.upload_script(
                account_id, script, code, _bindings(panel_uuid, host, endpoints, relays),
            )
            await cf.enable_workers_dev(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error
    await _announce(progress, 4)
    healthy, report = await _health(host, panel_uuid)
    _require_healthy(healthy, report)
    await _demote_dead_relays(report)
    uploaded = _endpoint_keys(endpoints)
    endpoints, rejected = await _ship(host, endpoints)
    if not endpoints:
        raise DeployError("no endpoint could complete a websocket upgrade")
    # A fully healed batch has rejected == []; compare with what was uploaded,
    # otherwise subscriptions silently keep every replaced dead endpoint.
    if _endpoint_keys(endpoints) != uploaded:
        try:
            async with CloudflareClient(token) as cf:
                await cf.upload_script(
                    account_id, script, code, _bindings(panel_uuid, host, endpoints, relays),
                )
        except CloudflareError as error:
            raise DeployError("could not publish the verified endpoint list") from error
    await _remember_reference(host)
    build_ms = int((time.perf_counter() - started) * 1000)
    log.info("panel built host=%s endpoints=%s rejected=%s healthy=%s in %sms",
             host, len(endpoints), len(rejected), healthy, build_ms)
    return Panel(
        account_id=account_id, script=script, host=host, uuid=panel_uuid,
        endpoints=endpoints, relays=relays, build_ms=build_ms,
        healthy=healthy, probe=report, rejected=len(rejected),
    )


async def refresh(panel: dict, force_scan: bool = False) -> Panel:
    """Keep the existing hostname and identity; don't churn an unhealthy worker."""
    token = panel.get("token")
    if not token:
        raise DeployError("no stored token for this panel")
    started = time.perf_counter()
    host, panel_uuid = str(panel["host"]), str(panel["uuid"])
    healthy, report = await _health(host, panel_uuid, attempts=3)
    _require_healthy(healthy, report)
    code = _read_worker()
    candidates = await _select_endpoints(force_scan)
    relays = await _select_relays()
    endpoints, rejected = await _ship(host, candidates)
    if not endpoints:
        raise DeployError("no endpoint could complete a websocket upgrade")
    try:
        async with CloudflareClient(token) as cf:
            await cf.upload_script(
                str(panel["account_id"]), str(panel["script_name"]), code,
                _bindings(panel_uuid, host, endpoints, relays),
            )
            await cf.enable_workers_dev(str(panel["account_id"]), str(panel["script_name"]))
    except CloudflareError as error:
        raise DeployError(error.message) from error
    healthy, report = await _health(host, panel_uuid, attempts=3)
    _require_healthy(healthy, report)
    await _demote_dead_relays(report)
    await _remember_reference(host)
    return Panel(
        account_id=str(panel["account_id"]), script=str(panel["script_name"]),
        host=host, uuid=panel_uuid, endpoints=endpoints, relays=relays,
        build_ms=int((time.perf_counter() - started) * 1000),
        healthy=healthy, probe=report, rejected=len(rejected),
    )


async def destroy(token: str, account_id: str, script: str) -> None:
    try:
        async with CloudflareClient(token) as cf:
            await cf.delete_script(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error
