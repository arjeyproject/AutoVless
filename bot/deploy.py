"""Turn a Cloudflare API token into a live VLESS panel.

The whole build is five steps, each reported back to the user:

  1. verify the token and resolve the account
  2. make sure a workers.dev subdomain exists
  3. pick clean entry points and relays
  4. upload the worker and expose it on workers.dev
  5. prove the tunnel is alive before calling it ready

``refresh`` does steps 3 to 5 only. It keeps the script name and the panel uuid,
so the subscription link never changes while the addresses under it do.
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
from .scanner import proxy_scanner, scanner

log = logging.getLogger("autovless.deploy")

STEP_KEYS: tuple[str, ...] = (
    "step_verify",
    "step_subdomain",
    "step_scan",
    "step_deploy",
    "step_health",
)

MARK_DONE = "\u2705"
MARK_ACTIVE = "\u23f3"
MARK_IDLE = "\u25ab\ufe0f"

Progress = Optional[Callable[[int], Awaitable[None]]]


class DeployError(Exception):
    """Raised when a build cannot be completed."""

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


def render_steps(lang: str, index: int, translate) -> str:
    """Checklist for the progress message."""
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
    except Exception:  # noqa: BLE001
        log.debug("progress update failed")


# --------------------------------------------------------------------- #
# network selection
# --------------------------------------------------------------------- #


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
    """Relays let the worker reach Cloudflare-fronted destinations.

    The worker walks this list in order, so one dead relay never takes the panel
    down with it. Scanned relays lead, long-lived seeds sit underneath as a
    floor, and the chain is always at least two deep.
    """
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
    """Plain text vars handed to the worker. Shared by build and refresh so the
    two paths can never drift apart."""
    return {
        "UUID": uuid,
        "PROXY_IP": ",".join(relays),
        "SUB_HOST": host,
        "BRAND": settings.brand,
        "WS_PATH": vless.WS_PATH,
        "ENDPOINTS": json.dumps(endpoints, ensure_ascii=False),
        "SUB_SOURCES": ",".join(settings.sub_sources),
        "CLEAN_DOMAINS": ",".join(settings.clean_domains),
        "SUB_REFRESH": str(settings.sub_refresh),
        "TLS_PORTS": ",".join(str(p) for p in settings.tls_ports),
        "HTTP_PORTS": ",".join(str(p) for p in settings.http_ports),
        "TLS_COUNT": str(settings.tls_config_count),
        "HTTP_COUNT": str(settings.http_config_count),
        "DNS_SERVER": settings.dns_server,
        "FALLBACK_HOST": settings.fallback_host,
        "BUILD_ID": str(int(time.time())),
    }


# --------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------- #


async def _health(host: str, uuid: str, attempts: Optional[int] = None) -> tuple[bool, dict]:
    """Wait for the hostname to publish, then prove outbound traffic works."""
    health_url = f"https://{host}/{uuid}/health"
    probe_url = f"https://{host}/{uuid}/probe"
    tries = attempts or settings.health_attempts

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        live = False
        for attempt in range(tries):
            try:
                response = await client.get(health_url)
                if response.status_code == 200 and response.json().get("ok"):
                    live = True
                    break
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(min(2 + attempt * 2, 8))

        if not live:
            return False, {}

        try:
            response = await client.get(probe_url)
            probe = response.json() if response.status_code == 200 else {}
        except Exception:  # noqa: BLE001
            probe = {}

    # A panel is healthy when the worker can open an outbound socket at all.
    # Relays are a bonus path, not the gate: plenty of destinations are reached
    # directly, and demanding a live relay used to mark working panels as dead.
    return bool(probe.get("ok")), probe


async def _demote_dead_relays(probe: dict) -> None:
    for relay in probe.get("relays") or []:
        if relay.get("ok"):
            continue
        target = str(relay.get("target") or "")
        host, _, port = target.partition(":")
        if host:
            await proxies.mark_fail(host, int(port) if port.isdigit() else 443)


# --------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------- #


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
                account_id,
                script,
                code,
                _bindings(panel_uuid, host, endpoints, relays),
            )
            await cf.enable_workers_dev(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error

    await _announce(progress, 4)
    healthy, probe = await _health(host, panel_uuid)
    if probe:
        await _demote_dead_relays(probe)

    build_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "panel built host=%s endpoints=%s relays=%s healthy=%s in %sms",
        host,
        len(endpoints),
        len(relays),
        healthy,
        build_ms,
    )

    return Panel(
        account_id=account_id,
        script=script,
        host=host,
        uuid=panel_uuid,
        endpoints=endpoints,
        relays=relays,
        build_ms=build_ms,
        healthy=healthy,
        probe=probe,
    )


async def refresh(panel: dict, force_scan: bool = False) -> Panel:
    """Re-point an existing panel at fresh entry addresses.

    Same account, same script, same uuid, same subscription URL: only the
    endpoint list and the relay chain change. This is what lets clean IPs be
    applied to every live config without anyone pressing rebuild.
    """
    token = panel.get("token")
    if not token:
        raise DeployError("no stored token for this panel")

    started = time.perf_counter()
    code = _read_worker()
    endpoints = await _select_endpoints(force_scan)
    relays = await _select_relays()
    host = str(panel["host"])
    panel_uuid = str(panel["uuid"])

    try:
        async with CloudflareClient(token) as cf:
            await cf.upload_script(
                str(panel["account_id"]),
                str(panel["script_name"]),
                code,
                _bindings(panel_uuid, host, endpoints, relays),
            )
            await cf.enable_workers_dev(str(panel["account_id"]), str(panel["script_name"]))
    except CloudflareError as error:
        raise DeployError(error.message) from error

    healthy, probe = await _health(host, panel_uuid, attempts=3)
    if probe:
        await _demote_dead_relays(probe)

    return Panel(
        account_id=str(panel["account_id"]),
        script=str(panel["script_name"]),
        host=host,
        uuid=panel_uuid,
        endpoints=endpoints,
        relays=relays,
        build_ms=int((time.perf_counter() - started) * 1000),
        healthy=healthy,
        probe=probe,
    )


async def destroy(token: str, account_id: str, script: str) -> None:
    try:
        async with CloudflareClient(token) as cf:
            await cf.delete_script(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error
