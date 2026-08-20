"""Deployment service: token to a live, config-serving Worker."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import httpx

from . import vless
from .cloudflare import CloudflareClient, CloudflareError, script_name
from .config import settings
from .scanner import scanner

log = logging.getLogger("autovless.deploy")

Progress = Callable[[int], Awaitable[None]]
STEPS = ("step_verify", "step_subdomain", "step_scan", "step_deploy", "step_health")

_worker_cache: dict[str, str] = {}


class DeployError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Panel:
    account_id: str
    script: str
    host: str
    uuid: str
    endpoints: list[dict] = field(default_factory=list)
    build_ms: int = 0
    healthy: bool = False


def worker_code() -> str:
    """Read the Worker bundle once and keep it in memory."""
    cached = _worker_cache.get("code")
    if cached:
        return cached
    path = settings.worker_file
    if not path.exists():
        raise DeployError(f"worker bundle is missing at {path}")
    code = path.read_text(encoding="utf-8")
    _worker_cache["code"] = code
    return code


async def _announce(progress: Optional[Progress], index: int) -> None:
    if progress is not None:
        try:
            await progress(index)
        except Exception:  # noqa: BLE001
            log.debug("progress callback failed", exc_info=True)


async def pick_endpoints(force_scan: bool = False) -> list[dict]:
    """Fastest verified endpoints, kicking off a scan when the pool is thin."""
    if force_scan:
        await scanner.scan_once(batch=max(320, settings.scan_batch // 3))

    endpoints = await vless.collect_endpoints(scanner)
    if len(endpoints) < settings.config_count:
        await scanner.scan_once(batch=max(320, settings.scan_batch // 3))
        endpoints = await vless.collect_endpoints(scanner)
    return endpoints


async def health_check(host: str, attempts: int = 8, delay: float = 2.5) -> bool:
    """Poll the fresh Worker until the Cloudflare edge starts serving it."""
    url = f"https://{host}/healthz"
    async with httpx.AsyncClient(timeout=8.0) as client:
        for attempt in range(attempts):
            try:
                response = await client.get(url)
                if response.status_code == 200 and response.json().get("ok"):
                    return True
            except (httpx.HTTPError, ValueError):
                pass
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
    return False


async def build(
    token: str,
    *,
    reuse: Optional[dict] = None,
    progress: Optional[Progress] = None,
    force_scan: bool = False,
) -> Panel:
    """Create or refresh a panel on the user's own Cloudflare account."""
    started = time.perf_counter()
    code = worker_code()

    async with CloudflareClient(token) as cf:
        try:
            await _announce(progress, 0)
            await cf.verify_token()
            account_id = (reuse or {}).get("account_id") or (await cf.first_account())["id"]

            await _announce(progress, 1)
            subdomain = await cf.ensure_subdomain(account_id)
            if not subdomain:
                raise DeployError("workers.dev subdomain is unavailable")

            await _announce(progress, 2)
            endpoints = await pick_endpoints(force_scan=force_scan)
            if not endpoints:
                raise DeployError("clean ip pool is empty")

            script = (reuse or {}).get("script_name") or script_name()
            uuid = (reuse or {}).get("uuid") or vless.new_uuid()
            host = f"{script}.{subdomain}.workers.dev"

            await _announce(progress, 3)
            await cf.upload_script(
                account_id,
                script,
                code,
                {
                    "UUID": uuid,
                    "PROXYIP": settings.proxy_ip,
                    "BRAND": settings.brand,
                    "IPS": json.dumps(endpoints, separators=(",", ":")),
                },
            )
            await cf.enable_workers_dev(account_id, script)
        except CloudflareError as error:
            raise DeployError(error.message) from error

    await _announce(progress, 4)
    healthy = await health_check(host)

    return Panel(
        account_id=account_id,
        script=script,
        host=host,
        uuid=uuid,
        endpoints=endpoints,
        build_ms=int((time.perf_counter() - started) * 1000),
        healthy=healthy,
    )


async def destroy(token: str, account_id: str, script: str) -> None:
    async with CloudflareClient(token) as cf:
        try:
            await cf.delete_script(account_id, script)
        except CloudflareError as error:
            raise DeployError(error.message) from error


def render_steps(lang: str, index: int, translate) -> str:
    """Checklist body for the progress message."""
    lines: list[str] = []
    for position, key in enumerate(STEPS):
        if position < index:
            marker = "\u2705"
        elif position == index:
            marker = "\u23f3"
        else:
            marker = "\u2b1c\ufe0f"
        lines.append(f"{marker} {translate(lang, key)}")
    return "\n".join(lines)
