"""Free configs, built by the same engine as the paid-for ones.

What "free" means here
---------------------
A user with no Cloudflare account gets a config on a *shared* AutoVless worker
that the admin registered once. Nothing about the config is fake: the entry
address comes out of the scanned clean-IP pool, it completes a real WebSocket
upgrade against that worker before it is handed over, and the subscription link
is the worker's own - so the entry addresses keep refreshing themselves long
after the message has scrolled away.

Three protocols come out of one server, because the worker sniffs the first frame
instead of asking: VLESS over WebSocket, Trojan over WebSocket (TLS ports only,
for the reason in the worker header) and both together. WireGuard/WARP is free
already and is handed out by the WARP screens.

Nothing here writes to the shared worker. It is read-only from the bot's side,
which is why one worker can serve every free user at once.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

from . import db, store, trojan, vless
from .config import settings
from .probe import measure
from .scanner import scanner

log = logging.getLogger("autovless.freepool")

PROTOCOLS = ("vless", "trojan", "mix")
DEFAULT_PATH = "/?ed=2560"
VERIFY_ROUNDS = 1
VERIFY_REQUIRED = 1
MAX_CONFIGS = 6

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


# --------------------------------------------------------------------- #
# registering servers
# --------------------------------------------------------------------- #


def parse(text: str) -> dict:
    """Accept either ``host uuid [password] [path]`` or a worker subscription URL."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty input")

    if raw.lower().startswith(("http://", "https://")):
        body = raw.split("://", 1)[1]
        parts = [part for part in body.split("/") if part]
        if len(parts) < 2:
            raise ValueError("that link has no uuid in it")
        host = parts[0].lower()
        found = _UUID.search(raw)
        uuid = (found.group(0) if found else parts[1]).lower()
        return {"host": host, "uuid": uuid, "password": uuid, "path": DEFAULT_PATH}

    bits = raw.replace("\t", " ").split()
    if len(bits) < 2:
        raise ValueError("send the host and the uuid")
    host = bits[0].lower().replace("https://", "").replace("http://", "").strip("/")
    uuid = bits[1].lower()
    password = bits[2] if len(bits) > 2 else uuid
    path = bits[3] if len(bits) > 3 else DEFAULT_PATH
    if not _UUID.match(uuid):
        raise ValueError("that does not look like a uuid")
    return {"host": host, "uuid": uuid, "password": password, "path": path}


async def add(text: str, label: str = "", source: str = "manual") -> dict:
    row = parse(text)
    server_id = await store.add_free_server(
        row["host"], row["uuid"], row["password"], row["path"], label or row["host"], source
    )
    healthy = await check_one({**row, "id": server_id})
    return {**row, "id": server_id, "healthy": healthy}


async def add_from_panel(tg_id: int) -> Optional[dict]:
    """Register the caller's own turbo panel as a free server."""
    panel = await db.get_panel(tg_id)
    if panel is None:
        return None
    server_id = await store.add_free_server(
        str(panel["host"]),
        str(panel["uuid"]),
        trojan.password_for(str(panel["uuid"])),
        vless.WS_PATH,
        f"panel:{tg_id}",
        "panel",
    )
    row = await store.free_server(server_id)
    if row:
        await check_one(row)
    return row


# --------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------- #


async def check_one(server: dict) -> bool:
    """A free server is healthy when its own worker answers ``/health``."""
    url = f"https://{server['host']}/{server['uuid']}/health"
    ok = False
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            ok = response.status_code == 200 and bool((response.json() or {}).get("ok"))
    except Exception:  # noqa: BLE001
        ok = False
    if server.get("id"):
        await store.mark_free_server(int(server["id"]), ok)
    return ok


async def check_all() -> tuple[int, int]:
    servers = await store.free_servers(active_only=False)
    healthy = 0
    for server in servers:
        if await check_one(server):
            healthy += 1
    return healthy, len(servers)


async def pick_server() -> Optional[dict]:
    """The healthiest server with the fewest handouts, so load spreads."""
    servers = await store.free_servers(active_only=True)
    if not servers:
        return None
    servers.sort(key=lambda row: (0 if row.get("healthy") else 1, int(row.get("hits") or 0)))
    return servers[0]


# --------------------------------------------------------------------- #
# links
# --------------------------------------------------------------------- #


def _remark(server: dict, endpoint: dict, index: int, protocol: str) -> str:
    secure = vless.is_tls(int(endpoint["port"]))
    badge = "\U0001f3af" if protocol == "trojan" else ("\u26a1" if secure else "\U0001f7e1")
    ping = f"{round(float(endpoint.get('latency') or 0))}ms" if endpoint.get("latency") else "auto"
    return (
        f"@{settings.brand} | {badge} FREE {protocol.upper()} | "
        f"{ping} | {endpoint.get('colo') or 'CF'} | #{index}"
    )


def _vless_link(server: dict, endpoint: dict, index: int) -> str:
    secure = vless.is_tls(int(endpoint["port"]))
    params = {
        "encryption": "none",
        "security": "tls" if secure else "none",
        "type": "ws",
        "host": server["host"],
        "path": server.get("path") or DEFAULT_PATH,
    }
    if secure:
        params.update({"sni": server["host"], "fp": "chrome", "alpn": "http/1.1"})
    query = urlencode(params, quote_via=quote, safe="")
    label = quote(_remark(server, endpoint, index, "vless"), safe="")
    return f"vless://{server['uuid']}@{endpoint['ip']}:{endpoint['port']}?{query}#{label}"


def _trojan_link(server: dict, endpoint: dict, index: int) -> str:
    params = {
        "security": "tls",
        "type": "ws",
        "host": server["host"],
        "path": server.get("path") or DEFAULT_PATH,
        "sni": server["host"],
        "fp": "chrome",
        "alpn": "http/1.1",
    }
    query = urlencode(params, quote_via=quote, safe="")
    password = server.get("password") or server["uuid"]
    label = quote(_remark(server, endpoint, index, "trojan"), safe="")
    return f"trojan://{quote(str(password), safe='')}@{endpoint['ip']}:{endpoint['port']}?{query}#{label}"


def sub_url(server: dict, protocol: str) -> str:
    tail = {"vless": "sub", "trojan": "trojan", "mix": "mix"}.get(protocol, "sub")
    return f"https://{server['host']}/{server['uuid']}/{tail}"


# --------------------------------------------------------------------- #
# building
# --------------------------------------------------------------------- #


async def _verified_endpoints(server: dict, tls_only: bool, count: int) -> list[dict]:
    """Clean addresses that complete a real handshake against *this* server."""
    tls_count = count if tls_only else max(2, count - 1)
    http_count = 0 if tls_only else max(1, count - tls_count)
    candidates = await vless.collect_endpoints(scanner, tls_count + 2, http_count + 1)
    if not candidates:
        await scanner.scan_once()
        candidates = await vless.collect_endpoints(scanner, tls_count + 2, http_count + 1)

    keep: list[dict] = []
    for endpoint in candidates:
        port = int(endpoint["port"])
        if tls_only and not vless.is_tls(port):
            continue
        result = await measure(
            str(endpoint["ip"]),
            port,
            tls=vless.is_tls(port),
            host=str(server["host"]),
            path=str(server.get("path") or DEFAULT_PATH),
            rounds=VERIFY_ROUNDS,
            required=VERIFY_REQUIRED,
            timeout=settings.accept_timeout,
        )
        if result is None:
            continue
        keep.append({**endpoint, **{"latency": result["latency"], "colo": result["colo"]}})
        if len(keep) >= count:
            break
    return keep


async def build(tg_id: int, protocol: str = "vless") -> Optional[dict]:
    """Everything the free screens need for one protocol, or None when nothing works."""
    protocol = protocol if protocol in PROTOCOLS else "vless"
    server = await pick_server()
    if server is None:
        return None

    tls_only = protocol == "trojan"
    endpoints = await _verified_endpoints(server, tls_only, MAX_CONFIGS)
    if not endpoints:
        return None

    links: list[str] = []
    for index, endpoint in enumerate(endpoints, start=1):
        if protocol in {"vless", "mix"}:
            links.append(_vless_link(server, endpoint, index))
        if protocol in {"trojan", "mix"} and vless.is_tls(int(endpoint["port"])):
            links.append(_trojan_link(server, endpoint, index))

    if not links:
        return None

    await store.record_free_grant(tg_id, int(server["id"]), protocol)
    best = min((float(row.get("latency") or 0) for row in endpoints if row.get("latency")), default=None)
    return {
        "protocol": protocol,
        "server": server,
        "host": str(server["host"]),
        "sub": sub_url(server, protocol),
        "links": links,
        "count": len(links),
        "best": best,
        "endpoints": endpoints,
    }


async def allowed(tg_id: int, is_admin: bool = False) -> tuple[bool, int]:
    """Free quota. ``0`` means unlimited, which is the default."""
    if is_admin:
        return True, 0
    limit = await store.get_int("free_per_user", 0)
    if limit <= 0:
        return True, 0
    used = await store.free_grants(tg_id)
    return used < limit, limit


async def stats() -> dict:
    pool = await db.pool_stats()
    warp = await db.warp_pool_stats()
    free = await store.free_stats()
    return {
        **free,
        "verified": int(pool.get("verified") or 0),
        "warp": int(warp.get("stable") or 0),
    }
