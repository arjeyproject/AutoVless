"""Turn a Cloudflare API token into a live VLESS panel.

The whole build is six steps, each reported back to the user:

  1. verify the token and resolve the account
  2. make sure a workers.dev subdomain exists
  3. pick clean entry points and relays
  4. upload the worker, expose it, and attach the user's own domain
  5. prove the tunnel is alive before calling it ready
  6. accept only the endpoints that answer a real WebSocket upgrade

The front door
--------------
The hostname a panel ships with is the single biggest factor in whether its
configs ping in Iran. ``workers.dev`` as SNI is filtered there, so a panel whose
configs carry it is dead on arrival no matter how clean the entry IPs are, and
the acceptance check below cannot see that because it runs from this server.
So when the user's Cloudflare account holds any active zone, the worker is
attached to ``<label>.<zone>`` (see ``bot.edge``) and that is the hostname every
config carries. workers.dev is kept only as the fallback for an account with no
domain, or a domain that never answers.

``refresh`` does steps 3 to 6 only, and also moves a workers.dev panel onto a
domain the moment one shows up on the account. Same script name, same uuid, so
the gateway subscription link never changes while the hostname and addresses
under it do.

One binding here is deliberately *not* chosen for speed. ``AI_PROXY_IP`` is the
relay every AI destination exits through, and the entire point of it is that the
address stops moving. That choice lives in ``bot.aipin``.

The Shadowsocks bindings travel with every upload too.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import httpx

from . import aipin, db, edge, proxies, shadowsocks, vless
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
    ai_country: str = ""
    build_ms: int = 0
    healthy: bool = False
    probe: dict = field(default_factory=dict)
    rejected: int = 0
    custom_domain: bool = False


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
    """Relays let the worker reach Cloudflare-fronted destinations."""
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


def _bindings(
    uuid: str,
    host: str,
    endpoints: list[dict],
    relays: list[str],
    ai_relays: Optional[list[str]] = None,
) -> dict[str, str]:
    """Plain text vars handed to the worker. Shared by build and refresh."""
    return {
        "UUID": uuid,
        "PROXY_IP": ",".join(relays),
        "AI_ROUTE": "true" if settings.ai_route else "false",
        "AI_PROXY_IP": ",".join(ai_relays or []),
        "AI_DOMAINS": ",".join(aipin.ai_domains()),
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
        **shadowsocks.bindings(uuid),
    }


# --------------------------------------------------------------------- #
# acceptance: no config ships without a 101
# --------------------------------------------------------------------- #


async def _accept(host: str, endpoints: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run the client's own handshake against this panel for every endpoint."""
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
    """Accept, then heal: replace what failed with something that passes."""
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


async def _published(host: str, uuid: str, attempts: Optional[int] = None) -> bool:
    """Has this hostname started answering for the panel yet?"""
    url = f"https://{host}/{uuid}/health"
    tries = attempts or settings.health_attempts
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for attempt in range(tries):
            try:
                response = await client.get(url)
                if response.status_code == 200 and response.json().get("ok"):
                    return True
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(min(2 + attempt * 2, 8))
    return False


async def _health(host: str, uuid: str, attempts: Optional[int] = None) -> tuple[bool, dict]:
    """Wait for the hostname to publish, then prove outbound traffic works."""
    if not await _published(host, uuid, attempts):
        return False, {}

    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            response = await client.get(f"https://{host}/{uuid}/probe")
            report = response.json() if response.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        report = {}

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


async def _record_pin(uuid: str, relays: list[str], country: str) -> None:
    if not relays:
        return
    try:
        await db.execute(
            "UPDATE panels SET ai_relay = ?, ai_country = ? WHERE uuid = ?",
            (relays[0], country, uuid),
        )
    except Exception:  # noqa: BLE001
        log.debug("could not record the ai pin on the panel row", exc_info=True)


async def _record_host(uuid: str, host: str) -> None:
    """The panel moved front doors: every screen and the gateway follow the row."""
    try:
        await db.execute("UPDATE panels SET host = ? WHERE uuid = ?", (host, uuid))
    except Exception:  # noqa: BLE001
        log.warning("could not record the new host %s for %s", host, uuid, exc_info=True)


async def _move_to_domain(token: str, account_id: str, script: str, uuid: str) -> str:
    """Attach a custom domain to a live workers.dev panel. ``""`` if none."""
    try:
        async with CloudflareClient(token) as cf:
            hostname = await edge.attach(cf, account_id, script)
    except CloudflareError as error:
        log.info("custom domain move skipped for %s: %s", script, error.message)
        return ""
    if not hostname:
        return ""
    if not await _published(hostname, uuid, attempts=6):
        log.warning("custom domain %s attached but not answering yet", hostname)
        return ""
    return hostname


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
    custom = ""

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
            dev_host = f"{script}.{subdomain}.workers.dev"
            ai_relays, ai_country = await aipin.choose(relays, panel_uuid)

            await _announce(progress, 3)
            await cf.upload_script(
                account_id,
                script,
                code,
                _bindings(panel_uuid, dev_host, endpoints, relays, ai_relays),
            )
            await cf.enable_workers_dev(account_id, script)
            # The script has to exist before a domain can point at it.
            custom = await edge.attach(cf, account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error

    await _announce(progress, 4)
    host = dev_host
    if custom:
        if await _published(custom, panel_uuid):
            host = custom
        else:
            log.warning("custom domain %s never answered, falling back to %s", custom, dev_host)

    healthy, report = await _health(host, panel_uuid)
    if report:
        await _demote_dead_relays(report)

    endpoints, rejected = await _ship(host, endpoints)
    if endpoints:
        await _remember_reference(host)
    if rejected or host != dev_host:
        # The worker serves its own subscription from ENDPOINTS and SUB_HOST, so
        # the healed list and the final hostname have to go back up.
        try:
            async with CloudflareClient(token) as cf:
                await cf.upload_script(
                    account_id,
                    script,
                    code,
                    _bindings(panel_uuid, host, endpoints, relays, ai_relays),
                )
        except CloudflareError as error:
            log.warning("could not re-upload the final bindings: %s", error.message)

    await _record_pin(panel_uuid, ai_relays, ai_country)
    build_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "panel built host=%s custom=%s endpoints=%s rejected=%s relays=%s ai=%s(%s) healthy=%s in %sms",
        host,
        host != dev_host,
        len(endpoints),
        len(rejected),
        len(relays),
        ",".join(ai_relays) or "none",
        ai_country or "??",
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
        ai_country=ai_country,
        build_ms=build_ms,
        healthy=healthy,
        probe=report,
        rejected=len(rejected),
        custom_domain=host != dev_host,
    )


async def refresh(panel: dict, force_scan: bool = False) -> Panel:
    """Re-point an existing panel at fresh entry addresses.

    Same account, same script, same uuid: only the endpoint list, the relay
    chain and - once, if the account has a domain - the front door change.
    """
    token = panel.get("token")
    if not token:
        raise DeployError("no stored token for this panel")

    started = time.perf_counter()
    code = _read_worker()
    account_id = str(panel["account_id"])
    script = str(panel["script_name"])
    host = str(panel["host"])
    panel_uuid = str(panel["uuid"])

    if edge.enabled() and edge.is_dev_host(host):
        moved = await _move_to_domain(str(token), account_id, script, panel_uuid)
        if moved:
            log.info("panel %s moved from %s to %s", panel_uuid, host, moved)
            host = moved
            await _record_host(panel_uuid, host)

    candidates = await _select_endpoints(force_scan)
    relays = await _select_relays()
    ai_relays, ai_country = await aipin.choose(relays, panel_uuid)

    endpoints, rejected = await _ship(host, candidates)
    if not endpoints:
        raise DeployError("no endpoint could complete a websocket upgrade")

    try:
        async with CloudflareClient(str(token)) as cf:
            await cf.upload_script(
                account_id,
                script,
                code,
                _bindings(panel_uuid, host, endpoints, relays, ai_relays),
            )
            await cf.enable_workers_dev(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error

    healthy, report = await _health(host, panel_uuid, attempts=3)
    if report:
        await _demote_dead_relays(report)
    if healthy:
        await _remember_reference(host)
    await _record_pin(panel_uuid, ai_relays, ai_country)

    return Panel(
        account_id=account_id,
        script=script,
        host=host,
        uuid=panel_uuid,
        endpoints=endpoints,
        relays=relays,
        ai_relays=ai_relays,
        ai_country=ai_country,
        build_ms=int((time.perf_counter() - started) * 1000),
        healthy=healthy,
        probe=report,
        rejected=len(rejected),
        custom_domain=not edge.is_dev_host(host),
    )


async def destroy(token: str, account_id: str, script: str) -> None:
    try:
        async with CloudflareClient(token) as cf:
            await cf.delete_script(account_id, script)
    except CloudflareError as error:
        raise DeployError(error.message) from error
