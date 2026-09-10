"""Turn a Cloudflare API token into a live VLESS panel.

The whole build is six steps, each reported back to the user:

  1. verify the token and resolve the account
  2. make sure a workers.dev subdomain exists
  3. pick clean entry points and relays
  4. upload the worker and expose it on workers.dev
  5. prove the tunnel is alive before calling it ready
  6. accept only the endpoints that answer a real WebSocket upgrade

Step 6 is the gate that matters. A panel used to ship whatever the pool offered;
now every address in a config has completed the client's own handshake against
this panel's own hostname, on its own port and path. Anything that fails is
demoted in the pool, replaced, and the worker is re-uploaded with the healed
list, so a user is never handed a config that cannot ping.

``refresh`` does steps 3 to 6 only. It keeps the script name and the panel uuid,
so the subscription link never changes while the addresses under it do.

One binding here is deliberately *not* chosen for speed. ``AI_PROXY_IP`` is the
relay every AI destination exits through, and the entire point of it is that the
address stops moving: a Cloudflare datacentre that changes on every refresh is
what makes ChatGPT and Gemini log a user out and start demanding verification. So
``_ai_relays`` pins by name and by panel uuid rather than by latency. Ordinary
traffic keeps the fastest-first chain, where a reshuffle costs nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
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
    "step_verify",
    "step_subdomain",
    "step_scan",
    "step_deploy",
    "step_health",
)

MARK_DONE = "\u2705"
MARK_ACTIVE = "\u23f3"
MARK_IDLE = "\u25ab\ufe0f"

# Acceptance is deliberately stricter than the sweep: three tries, two hits.
# One blip must not drop a good address, and one lucky answer must not promote a
# bad one.
ACCEPT_ROUNDS = 3
ACCEPT_REQUIRED = 2

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
    ai_relays: list[str] = field(default_factory=list)
    build_ms: int = 0
    healthy: bool = False
    probe: dict = field(default_factory=dict)
    rejected: int = 0


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


def _ai_relays(relays: list[str], panel_uuid: str) -> list[str]:
    """Which relays AI destinations exit through, chosen to *stay the same*.

    An explicit ``AI_PROXY_IP`` wins outright: an operator who has a static
    address wants that address and nothing else.

    Otherwise the pick is derived from the relay list - but from a copy sorted by
    name, not the latency ordering ``_select_relays`` produced. That distinction
    is the whole point. Latency ordering changes on every refresh, so pinning to
    the head of it would hand the user a different exit IP every time the
    autopilot ran, which is precisely the behaviour these sites read as account
    abuse. Sorting by name means the same relay set always yields the same pin,
    and the panel uuid spreads different users across different relays so one
    address does not carry everybody.
    """
    if settings.ai_proxy_ip:
        return list(settings.ai_proxy_ip)
    if not relays:
        return []
    stable = sorted(set(relays))
    seed = f"{settings.secret_key}:{panel_uuid}".encode("utf-8")
    offset = hashlib.sha256(seed).digest()[0] % len(stable)
    ordered = stable[offset:] + stable[:offset]
    return ordered[: max(1, settings.ai_relays)]


def _bindings(uuid: str, host: str, endpoints: list[dict], relays: list[str]) -> dict[str, str]:
    """Plain text vars handed to the worker. Shared by build and refresh so the
    two paths can never drift apart."""
    return {
        "UUID": uuid,
        "PROXY_IP": ",".join(relays),
        "AI_ROUTE": "true" if settings.ai_route else "false",
        "AI_PROXY_IP": ",".join(_ai_relays(relays, uuid)),
        "AI_DOMAINS": ",".join(settings.ai_domains),
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
# acceptance: no config ships without a 101
# --------------------------------------------------------------------- #


async def _accept(host: str, endpoints: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run the client's own handshake against this panel for every endpoint.

    Survivors come back with the latency the client will actually see, measured
    end to end through the worker, which is also what ends up printed in the
    config name.
    """
    keep: list[dict] = []
    dead: list[dict] = []

    for endpoint in endpoints:
        port = int(endpoint["port"])
        result = await measure(
            str(endpoint["ip"]),
            port,
            tls=vless.is_tls(port),
            host=host,
            path=vless.WS_PATH,
            rounds=ACCEPT_ROUNDS,
            required=ACCEPT_REQUIRED,
            timeout=settings.accept_timeout,
        )
        if result is None:
            log.info("rejected %s:%s for %s, no websocket upgrade", endpoint["ip"], port, host)
            await scanner.demote(str(endpoint["ip"]), port)
            dead.append(endpoint)
            continue
        keep.append(
            {
                **endpoint,
                "latency": result["latency"],
                "jitter": result["jitter"],
                "colo": result["colo"],
                "verified": True,
            }
        )

    return keep, dead


async def _ship(host: str, endpoints: list[dict]) -> tuple[list[dict], list[dict]]:
    """Accept, then heal: replace what failed with something that passes.

    Replacements are drawn from the same group as the endpoint they stand in
    for, so a TLS slot never quietly becomes a plain one. If the pool has
    nothing left that works, the panel ships short on purpose. Four configs that
    ping beat nine that do not.
    """
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
            candidates += await vless.spare_endpoints(
                scanner, settings.tls_ports, missing_tls * 3, seen
            )
        if missing_http:
            candidates += await vless.spare_endpoints(
                scanner, settings.http_ports, missing_http * 3, seen
            )
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
            "shipping %s endpoints, %s could not be replaced: %s",
            len(keep),
            len(dead),
            ", ".join(f"{item['ip']}:{item['port']}" for item in dead),
        )
    return keep, dead


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
            report = response.json() if response.status_code == 200 else {}
        except Exception:  # noqa: BLE001
            report = {}

    # A panel is healthy when the worker can open an outbound socket at all.
    # Relays are a bonus path, not the gate: plenty of destinations are reached
    # directly, and demanding a live relay used to mark working panels as dead.
    return bool(report.get("ok")), report


async def _demote_dead_relays(report: dict) -> None:
    for relay in report.get("relays") or []:
        if relay.get("ok"):
            continue
        target = str(relay.get("target") or "")
        host, _, port = target.partition(":")
        if host:
            await proxies.mark_fail(host, int(port) if port.isdigit() else 443)


async def _remember_reference(host: str) -> None:
    """Hand the sweep a real hostname to verify TLS ports against."""
    try:
        await db.set_option("verify_host", host.lower())
    except Exception:  # noqa: BLE001
        log.debug("could not record verification host")


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
    healthy, report = await _health(host, panel_uuid)
    if report:
        await _demote_dead_relays(report)

    endpoints, rejected = await _ship(host, endpoints)
    if endpoints:
        await _remember_reference(host)
    if rejected:
        # The worker serves its own subscription from ENDPOINTS, so the healed
        # list has to go back up or clients would keep pulling the dead rows.
        try:
            async with CloudflareClient(token) as cf:
                await cf.upload_script(
                    account_id,
                    script,
                    code,
                    _bindings(panel_uuid, host, endpoints, relays),
                )
        except CloudflareError as error:
            log.warning("could not re-upload the healed endpoint list: %s", error.message)

    ai_relays = _ai_relays(relays, panel_uuid)
    build_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "panel built host=%s endpoints=%s rejected=%s relays=%s ai=%s healthy=%s in %sms",
        host,
        len(endpoints),
        len(rejected),
        len(relays),
        ",".join(ai_relays) or "none",
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
        ai_relays=ai_relays,
        build_ms=build_ms,
        healthy=healthy,
        probe=report,
        rejected=len(rejected),
    )


async def refresh(panel: dict, force_scan: bool = False) -> Panel:
    """Re-point an existing panel at fresh entry addresses.

    Same account, same script, same uuid, same subscription URL: only the
    endpoint list and the relay chain change. This is what lets clean IPs be
    applied to every live config without anyone pressing rebuild.

    The AI pin is derived from the uuid, which does not change here, so a refresh
    keeps the same exit address for AI traffic even as the ordinary chain is
    reshuffled by latency underneath it.
    """
    token = panel.get("token")
    if not token:
        raise DeployError("no stored token for this panel")

    started = time.perf_counter()
    code = _read_worker()
    candidates = await _select_endpoints(force_scan)
    relays = await _select_relays()
    host = str(panel["host"])
    panel_uuid = str(panel["uuid"])

    # The panel is already live, so acceptance can run before the upload here:
    # the addresses are tested against the hostname that is serving right now.
    endpoints, rejected = await _ship(host, candidates)
    if not endpoints:
        raise DeployError("no endpoint could complete a websocket upgrade")

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

    healthy, report = await _health(host, panel_uuid, attempts=3)
    if report:
        await _demote_dead_relays(report)
    if healthy:
        await _remember_reference(host)

    return Panel(
        account_id=str(panel["account_id"]),
        script=str(panel["script_name"]),
        host=host,
        uuid=panel_uuid,
        endpoints=endpoints,
        relays=relays,
        ai_relays=_ai_relays(relays, panel_uuid),
        build_ms=int((time.perf_counter() - started) * 1000),
        healthy=healthy,
        probe=report,
        rejected=len(rejected),
    )


async def destroy(token: str, account_id: str, script: str) -> None:
    try:
        async with CloudflareClient(token) as cf:
            await cf.delete_script(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error
