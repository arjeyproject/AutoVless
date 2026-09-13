"""HTTP API for the Telegram Mini App, and the server that hosts the app itself.

Why the mini app needs a backend at all
--------------------------------------
The first version was a static page with a base64 payload in the URL. It could
show what the bot already knew and nothing else: no build, no rebuild, no WARP,
no free config. Everything in the bot that *does* something needs the database
and the Cloudflare API, so it needs a server, and that server is here.

Trust
-----
Telegram signs every mini app launch. ``initData`` arrives with an HMAC computed
under a key derived from the bot token, so verifying it proves the caller is the
Telegram user it claims to be - no session, no password, nothing to steal. Every
endpoint except ``/api/health`` verifies it, and the user id comes out of the
signed payload rather than out of anything the client sent separately.

Serving
-------
The same aiohttp app serves ``webapp/`` at ``/`` and the API under ``/api``. That
is deliberate: a Telegram mini app must be HTTPS, and a page on HTTPS cannot call
an HTTP API, so one origin behind one certificate is the only arrangement that
works without a second domain. Put any TLS terminator in front of it (the docs
use Caddy, two lines) and point ``WEBAPP_URL`` at it.

Long jobs
---------
Building a panel takes the better part of a minute, which is longer than a mobile
browser will hold a request open. ``/api/panel/build`` therefore returns a job id
immediately and the app polls ``/api/job/{id}`` for the same five step checklist
the bot draws in chat.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qsl

from aiohttp import web

from . import (
    aipin,
    db,
    deploy,
    fragment,
    freepool,
    proxies,
    referral,
    store,
    trojan,
    vless,
    warp,
    warpconf,
)
from .autopilot import autopilot
from .config import BASE_DIR, settings
from .platforms import ORDER as PLATFORM_ORDER
from .platforms import normalise_platform
from .scanner import proxy_scanner, scanner
from .utils import tcp_latency

log = logging.getLogger("autovless.api")

WEBAPP_DIR = Path(os.getenv("WEBAPP_DIR") or (BASE_DIR / "webapp"))
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
API_PORT = int(os.getenv("API_PORT", "8088") or 8088)
API_ENABLED = (os.getenv("API_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"})
INIT_DATA_TTL = int(os.getenv("INIT_DATA_TTL", "86400") or 86400)

JOB_TTL = 900
_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()


# --------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------- #


def verify_init_data(raw: str) -> Optional[dict]:
    """The Telegram user behind a mini app launch, or None if the signature fails."""
    if not raw or not settings.bot_token:
        return None

    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    given = pairs.pop("hash", "")
    if not given:
        return None

    check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, given):
        return None

    try:
        issued = int(pairs.get("auth_date") or 0)
    except ValueError:
        issued = 0
    if INIT_DATA_TTL and issued and time.time() - issued > INIT_DATA_TTL:
        return None

    try:
        user = json.loads(pairs.get("user") or "{}")
    except ValueError:
        return None
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return user


def _init_data(request: web.Request, body: dict) -> str:
    return (
        request.headers.get("X-Init-Data")
        or str(body.get("initData") or "")
        or request.query.get("initData", "")
    )


async def _body(request: web.Request) -> dict:
    if request.method == "GET":
        return dict(request.query)
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def _json(payload: Any, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status, dumps=lambda item: json.dumps(item, ensure_ascii=False))


Handler = Callable[[web.Request, dict, dict], Awaitable[web.StreamResponse]]

# Reachable even when the invite lock is closed.
OPEN_WHILE_LOCKED = {"/api/state", "/api/settings", "/api/referral", "/api/health"}


def guarded(handler: Handler, admin_only: bool = False) -> Callable:
    """Verify the launch signature, then hand the handler the user and the body."""

    async def wrapper(request: web.Request) -> web.StreamResponse:
        body = await _body(request)
        user = verify_init_data(_init_data(request, body))
        if user is None:
            return _json({"ok": False, "error": "unauthorised"}, status=401)

        tg_id = int(user["id"])
        row = await db.upsert_user(tg_id, user.get("username"), user.get("first_name"))
        if row["is_banned"] and not settings.is_admin(tg_id):
            return _json({"ok": False, "error": "banned"}, status=403)
        if admin_only and not settings.is_admin(tg_id):
            return _json({"ok": False, "error": "admins only"}, status=403)

        # The invite lock applies here too, or the mini app would be a way around
        # it. State, settings and the invite screen itself stay open, because those
        # are what a locked user needs to see to get unlocked.
        if request.path not in OPEN_WHILE_LOCKED and not await referral.unlocked(
            tg_id, settings.is_admin(tg_id)
        ):
            return _json(
                {
                    "ok": False,
                    "error": "locked",
                    "required": await referral.required(),
                    "invited": await referral.invited(tg_id),
                },
                status=403,
            )

        try:
            return await handler(request, body, {"id": tg_id, "row": row, "raw": user})
        except web.HTTPException:
            raise
        except Exception as error:  # noqa: BLE001
            log.exception("api handler failed: %s", request.path)
            return _json({"ok": False, "error": str(error)}, status=500)

    return wrapper


# --------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------- #


async def _lang(tg_id: int, row: Any) -> str:
    lang = str((row["lang"] if row is not None else "") or settings.default_lang).lower()
    return lang if lang in {"fa", "en"} else settings.default_lang


async def _panel_payload(tg_id: int) -> Optional[dict]:
    panel = await db.get_panel(tg_id)
    if panel is None:
        return None
    uuid = str(panel["uuid"])
    host = str(panel["host"])
    endpoints = list(panel.get("endpoints") or [])
    pin = await store.ai_pin(uuid)
    return {
        "host": host,
        "uuid": uuid,
        "healthy": bool(panel.get("healthy")),
        "rebuilds": int(panel.get("rebuilds") or 0),
        "syncs": int(panel.get("syncs") or 0),
        "updatedAt": int(panel.get("updated_at") or 0),
        "syncedAt": int(panel.get("synced_at") or 0),
        "hasToken": bool(panel.get("token")),
        "endpoints": endpoints,
        "trojanPassword": trojan.password_for(uuid),
        "aiRelay": (pin or {}).get("relay"),
        "aiCountry": (pin or {}).get("country"),
        "links": {
            "sub": vless.sub_url(uuid, host),
            "raw": vless.sub_url(uuid, host, "raw"),
            "mix": vless.sub_url(uuid, host, "mix"),
            "trojan": trojan.sub_url(uuid, host),
            "clash": vless.sub_url(uuid, host, "clash"),
            "singbox": vless.sub_url(uuid, host, "singbox"),
        },
        "vless": vless.build_links(uuid, host, endpoints, settings.brand),
        "trojan": trojan.build_links(uuid, host, endpoints),
    }


async def _warp_payload(tg_id: int) -> dict:
    row = await db.get_warp_user(tg_id)
    endpoints = await db.best_warp_endpoints(8, stable_only=True)
    if not endpoints:
        endpoints = await db.best_warp_endpoints(8, stable_only=False)
    payload = {
        "hasIdentity": row is not None,
        "accountType": str((row or {}).get("account_type") or "free"),
        "endpoints": [dict(item) for item in endpoints],
        "platforms": list(PLATFORM_ORDER),
    }
    if row is not None:
        identity = dict(row.get("identity") or {})
        payload["addresses"] = {"v4": identity.get("v4"), "v6": identity.get("v6")}
        payload["refreshes"] = int(row.get("refreshes") or 0)
    return payload


async def state_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    row = user["row"]
    lang = await _lang(tg_id, row)
    pool = await db.pool_stats()
    relays = await proxy_scanner.stats()
    warp_pool = await db.warp_pool_stats()
    free = await freepool.stats()
    goal = await referral.required()
    invited = await referral.invited(tg_id)

    return _json(
        {
            "ok": True,
            "brand": settings.brand,
            "user": {
                "id": tg_id,
                "name": row["first_name"],
                "username": row["username"],
                "lang": lang,
                "theme": await store.get_theme(tg_id),
                "isAdmin": settings.is_admin(tg_id),
                "builds": int(row["builds"] or 0),
            },
            "stats": {
                "pool": int(pool.get("total") or 0),
                "verified": int(pool.get("verified") or 0),
                "fresh": int(pool.get("fresh") or 0),
                "best": pool.get("best"),
                "domains": int(pool.get("domains") or 0),
                "relays": int(relays.get("verified") or 0),
                "warp": int(warp_pool.get("stable") or 0),
                "updatedAt": int(pool.get("updated_at") or 0),
            },
            "panel": await _panel_payload(tg_id),
            "warp": await _warp_payload(tg_id),
            "free": {
                "enabled": bool(free.get("enabled")),
                "servers": int(free.get("servers") or 0),
                "healthy": int(free.get("healthy") or 0),
                "protocols": list(freepool.PROTOCOLS),
            },
            "referral": {
                "enabled": await referral.enabled(),
                "required": goal,
                "invited": invited,
                "unlocked": await referral.unlocked(tg_id, settings.is_admin(tg_id)),
                "link": referral.link(referral.cached_username(), tg_id),
            },
            "links": {
                "support": settings.support_url,
                "channel": settings.channel_url,
                "github": settings.github_url,
                "donate": settings.donate_url,
            },
        }
    )


async def settings_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    lang = str(body.get("lang") or "").lower()
    theme = str(body.get("theme") or "").lower()
    if lang in {"fa", "en"}:
        await db.set_lang(tg_id, lang)
    if theme in {"auto", "dark", "light"}:
        await store.set_theme(tg_id, theme)
    return _json({"ok": True, "lang": lang, "theme": theme})


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #


def _new_job(kind: str) -> str:
    _reap_jobs()
    job_id = secrets.token_urlsafe(9)
    _jobs[job_id] = {"kind": kind, "state": "running", "step": 0, "at": time.time()}
    return job_id


def _reap_jobs() -> None:
    cutoff = time.time() - JOB_TTL
    for job_id in [key for key, value in _jobs.items() if value.get("at", 0) < cutoff]:
        _jobs.pop(job_id, None)


def _spawn(coro: Awaitable[Any], name: str) -> None:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_build(job_id: str, tg_id: int, token: str, reuse: Optional[dict]) -> None:
    job = _jobs[job_id]

    async def progress(step: int) -> None:
        job["step"] = int(step)
        job["at"] = time.time()

    try:
        panel = await deploy.build(token, reuse=reuse, progress=progress, force_scan=True)
    except deploy.DeployError as error:
        job.update({"state": "failed", "error": error.reason, "at": time.time()})
        return
    except Exception as error:  # noqa: BLE001
        log.exception("mini app build failed")
        job.update({"state": "failed", "error": str(error), "at": time.time()})
        return

    await db.save_panel(
        tg_id,
        panel.account_id,
        panel.script,
        panel.host,
        panel.uuid,
        token,
        panel.endpoints,
        panel.build_ms,
        relays=panel.relays,
        healthy=panel.healthy,
    )
    await db.log_event("miniapp_build", tg_id, panel.host)
    job.update(
        {
            "state": "done",
            "step": len(deploy.STEP_KEYS),
            "at": time.time(),
            "result": await _panel_payload(tg_id),
        }
    )


async def build_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    if not await db.get_flag("builds_enabled") and not settings.is_admin(user["id"]):
        return _json({"ok": False, "error": "builds are disabled"}, status=403)

    tg_id = user["id"]
    token = str(body.get("token") or "").strip()
    reuse: Optional[dict] = None

    panel = await db.get_panel(tg_id)
    if str(body.get("mode") or "") == "rebuild" and panel is not None:
        reuse = {
            "account_id": panel["account_id"],
            "script_name": panel["script_name"],
            "uuid": panel["uuid"],
        }
        token = token or str(panel.get("token") or "")

    if not token:
        return _json({"ok": False, "error": "cloudflare token is required"}, status=400)

    job_id = _new_job("build")
    _spawn(_run_build(job_id, tg_id, token, reuse), f"api-build-{tg_id}")
    return _json({"ok": True, "job": job_id, "steps": list(deploy.STEP_KEYS)})


async def job_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    job = _jobs.get(request.match_info.get("job", ""))
    if job is None:
        return _json({"ok": False, "error": "unknown job"}, status=404)
    return _json({"ok": True, "job": {key: value for key, value in job.items() if key != "at"}})


async def apply_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """The same operation the autopilot runs, on demand. Keeps the same link."""
    tg_id = user["id"]
    panel = await db.get_panel(tg_id)
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)
    if not panel.get("token"):
        return _json({"ok": False, "error": "no stored token"}, status=400)

    try:
        result = await autopilot.refresh_panel(tg_id, force_scan=True)
    except deploy.DeployError as error:
        return _json({"ok": False, "error": error.reason}, status=502)
    if result is None:
        return _json({"ok": False, "error": "no stored token"}, status=400)

    return _json({"ok": True, "healthy": bool(result["healthy"]), "panel": await _panel_payload(tg_id)})


async def delete_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    panel = await db.get_panel(tg_id)
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)
    token = panel.get("token")
    if token:
        try:
            await deploy.destroy(token, panel["account_id"], panel["script_name"])
        except deploy.DeployError as error:
            log.warning("worker delete from mini app failed: %s", error.reason)
    await db.delete_panel(tg_id)
    await db.log_event("panel_deleted", tg_id, str(panel["host"]))
    return _json({"ok": True})


async def export_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Client config files, rendered by the same code the bot's buttons use."""
    tg_id = user["id"]
    panel = await db.get_panel(tg_id)
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)

    kind = str(body.get("format") or request.query.get("format") or "clash").lower()
    uuid, host = str(panel["uuid"]), str(panel["host"])
    endpoints = list(panel.get("endpoints") or [])

    if kind == "clash":
        payload, name = vless.build_clash(uuid, host, endpoints), "autovless-clash.yaml"
    elif kind in {"singbox", "sing-box"}:
        payload, name = vless.build_singbox(uuid, host, endpoints), "autovless-singbox.json"
    elif kind == "fragment":
        payload, name = fragment.xray_config(uuid, host, endpoints), fragment.filename()
    elif kind == "trojan":
        payload, name = "\n".join(trojan.build_links(uuid, host, endpoints)), "autovless-trojan.txt"
    else:
        payload, name = "\n".join(vless.build_links(uuid, host, endpoints, settings.brand)), "autovless.txt"

    return _json({"ok": True, "filename": name, "body": payload})


async def ping_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    panel = await db.get_panel(user["id"])
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)
    endpoints = list(panel.get("endpoints") or [])
    results = await asyncio.gather(
        *(tcp_latency(str(item["ip"]), int(item["port"])) for item in endpoints)
    )
    return _json(
        {
            "ok": True,
            "rows": [
                {
                    "ip": str(item["ip"]),
                    "port": int(item["port"]),
                    "kind": item.get("kind") or "ip",
                    "latency": latency,
                }
                for item, latency in zip(endpoints, results)
            ],
        }
    )


async def rescan_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    _spawn(scanner.scan_once(batch=max(320, settings.scan_batch // 3)), "api-rescan")
    return _json({"ok": True})


# --------------------------------------------------------------------- #
# warp
# --------------------------------------------------------------------- #


async def warp_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """A real WireGuard/WARP config, rendered for the platform the app asked for."""
    if not await db.get_flag("warp_enabled") and not settings.is_admin(user["id"]):
        return _json({"ok": False, "error": "warp is disabled"}, status=403)

    tg_id = user["id"]
    platform = normalise_platform(body.get("platform"))
    family = str(body.get("family") or "v4").lower()
    kind = str(body.get("kind") or "").lower() or None

    row = await db.get_warp_user(tg_id)
    if row is None or body.get("fresh"):
        try:
            identity = await warp.provision()
        except warp.WarpError as error:
            return _json({"ok": False, "error": str(error)}, status=502)
        await db.save_warp_user(tg_id, identity, [])
    else:
        identity = dict(row.get("identity") or {})

    endpoints = await db.best_warp_endpoints(12, stable_only=True)
    if not endpoints:
        endpoints = await db.best_warp_endpoints(12, stable_only=False)
    rows = [dict(item) for item in endpoints]
    if family == "v6":
        rows = [item for item in rows if ":" in str(item["ip"])] or rows
    else:
        rows = [item for item in rows if ":" not in str(item["ip"])] or rows

    await db.update_warp_endpoints(tg_id, rows[:6])
    profile = warp.obfuscation(identity.get("private_key", ""))
    conf = warpconf.conf_for(identity, rows, platform=platform, kind=kind or "", profile=profile)

    return _json(
        {
            "ok": True,
            "platform": platform,
            "family": family,
            "clean": warpconf.is_clean_for(platform),
            "endpoint": warpconf.label(rows, 0, platform),
            "filename": warpconf.filename(family, kind or "awg", platform),
            "conf": conf,
            "link": warp.warp_link(identity, rows),
            "singbox": warp.singbox_json(identity, rows),
            "clash": warp.clash_yaml(identity, rows),
        }
    )


# --------------------------------------------------------------------- #
# free pool
# --------------------------------------------------------------------- #


async def free_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    if not await store.flag("free_enabled", True):
        return _json({"ok": False, "error": "disabled"}, status=403)

    allowed, limit = await freepool.allowed(tg_id, settings.is_admin(tg_id))
    if not allowed:
        return _json({"ok": False, "error": "quota", "limit": limit}, status=429)

    protocol = str(body.get("protocol") or "vless").lower()
    result = await freepool.build(tg_id, protocol)
    if result is None:
        return _json({"ok": False, "error": "nothing passed the handshake test"}, status=503)

    await db.log_event("miniapp_free", tg_id, f"{protocol} links={result['count']}")
    return _json(
        {
            "ok": True,
            "protocol": result["protocol"],
            "host": result["host"],
            "sub": result["sub"],
            "links": result["links"],
            "best": result["best"],
            "count": result["count"],
        }
    )


# --------------------------------------------------------------------- #
# referral
# --------------------------------------------------------------------- #


async def referral_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    goal = await referral.required()
    done = await referral.invited(tg_id)
    return _json(
        {
            "ok": True,
            "enabled": await referral.enabled(),
            "required": goal,
            "invited": done,
            "left": max(0, goal - done),
            "unlocked": await referral.unlocked(tg_id, settings.is_admin(tg_id)),
            "link": referral.link(referral.cached_username(), tg_id),
            "top": await store.referral_top(10),
        }
    )


# --------------------------------------------------------------------- #
# admin
# --------------------------------------------------------------------- #

ADMIN_FLAGS = (
    "maintenance",
    "builds_enabled",
    "force_join",
    "warp_enabled",
    "support_enabled",
    "autopilot",
    "curator",
    "referral_lock",
    "free_enabled",
    "miniapp_enabled",
)


async def admin_state_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    return _json(
        {
            "ok": True,
            "stats": await db.global_stats(),
            "pool": await db.pool_stats(),
            "flags": {key: await db.get_flag(key) for key in ADMIN_FLAGS},
            "referral": await store.referral_stats(),
            "free": await store.free_stats(),
            "ai": await aipin.report(),
            "events": await db.recent_events(12),
        }
    )


async def admin_flag_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    key = str(body.get("key") or "")
    if key not in ADMIN_FLAGS:
        return _json({"ok": False, "error": "unknown option"}, status=400)
    state = await db.toggle_flag(key)
    await db.log_event("option", user["id"], f"{key}={state}")
    return _json({"ok": True, "key": key, "value": state})


async def admin_referral_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    if "required" in body:
        try:
            value = max(0, min(referral.MAX_REQUIRED, int(body["required"])))
        except (TypeError, ValueError):
            return _json({"ok": False, "error": "not a number"}, status=400)
        await store.set_int("referral_required", value)
        await db.log_event("option", user["id"], f"referral_required={value}")
    return _json({"ok": True, "referral": await store.referral_stats()})


async def admin_free_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    action = str(body.get("action") or "list")
    if action == "add":
        try:
            row = await freepool.add(str(body.get("value") or ""))
        except ValueError as error:
            return _json({"ok": False, "error": str(error)}, status=400)
        return _json({"ok": True, "server": row})
    if action == "panel":
        row = await freepool.add_from_panel(user["id"])
        if row is None:
            return _json({"ok": False, "error": "no panel"}, status=404)
        return _json({"ok": True, "server": dict(row)})
    if action == "check":
        healthy, total = await freepool.check_all()
        return _json({"ok": True, "healthy": healthy, "total": total})
    if action in {"delete", "toggle"}:
        try:
            server_id = int(body.get("id") or 0)
        except (TypeError, ValueError):
            return _json({"ok": False, "error": "bad id"}, status=400)
        if action == "delete":
            await store.remove_free_server(server_id)
        else:
            await store.toggle_free_server(server_id)
    return _json({"ok": True, "servers": await store.free_servers(active_only=False)})


async def admin_ai_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    if str(body.get("action") or "") == "geo":
        rows = await proxies.best(60, verified_only=False)
        await proxies.ensure_countries([row["host"] for row in rows])
    return _json({"ok": True, "ai": await aipin.report()})


# --------------------------------------------------------------------- #
# qr
# --------------------------------------------------------------------- #


async def qr_handler(request: web.Request) -> web.StreamResponse:
    """A PNG for any text, so the app never needs a QR library of its own."""
    text = request.query.get("text", "").strip()
    if not text or len(text) > 2000:
        return _json({"ok": False, "error": "bad text"}, status=400)
    try:
        import qrcode
    except ImportError:
        return _json({"ok": False, "error": "qrcode is not installed"}, status=501)

    image = qrcode.make(text, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return web.Response(
        body=buffer.getvalue(),
        content_type="image/png",
        headers={"cache-control": "no-store", "access-control-allow-origin": "*"},
    )


# --------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------- #


async def static_handler(request: web.Request) -> web.StreamResponse:
    """Serve the mini app out of ``webapp/``, and nothing outside it."""
    root = WEBAPP_DIR.resolve()
    relative = (request.match_info.get("tail") or "").strip("/") or "index.html"
    target = (root / relative).resolve()
    if root not in target.parents and target != root:
        raise web.HTTPNotFound()
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        target = root / "index.html"
    if not target.is_file():
        raise web.HTTPNotFound()
    cache = "no-cache" if target.suffix in {".html", ".json"} else "public, max-age=3600"
    return web.FileResponse(target, headers={"cache-control": cache})


@web.middleware
async def cors(request: web.Request, handler: Callable) -> web.StreamResponse:
    """The app is usually same-origin, but GitHub Pages hosting is still supported."""
    if request.method == "OPTIONS":
        response: web.StreamResponse = web.Response(status=204)
    else:
        response = await handler(request)
    response.headers["access-control-allow-origin"] = "*"
    response.headers["access-control-allow-headers"] = "content-type, x-init-data"
    response.headers["access-control-allow-methods"] = "GET, POST, OPTIONS"
    return response


async def health_handler(request: web.Request) -> web.StreamResponse:
    return _json({"ok": True, "brand": settings.brand, "webapp": WEBAPP_DIR.exists()})


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors])
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/qr", qr_handler)

    routes = (
        ("POST", "/api/state", guarded(state_handler), False),
        ("POST", "/api/settings", guarded(settings_handler), False),
        ("POST", "/api/panel/build", guarded(build_handler), False),
        ("GET", "/api/job/{job}", guarded(job_handler), False),
        ("POST", "/api/panel/apply", guarded(apply_handler), False),
        ("POST", "/api/panel/delete", guarded(delete_handler), False),
        ("POST", "/api/panel/export", guarded(export_handler), False),
        ("POST", "/api/panel/ping", guarded(ping_handler), False),
        ("POST", "/api/rescan", guarded(rescan_handler), False),
        ("POST", "/api/warp/build", guarded(warp_handler), False),
        ("POST", "/api/free/build", guarded(free_handler), False),
        ("POST", "/api/referral", guarded(referral_handler), False),
        ("POST", "/api/admin/state", guarded(admin_state_handler, admin_only=True), True),
        ("POST", "/api/admin/flag", guarded(admin_flag_handler, admin_only=True), True),
        ("POST", "/api/admin/referral", guarded(admin_referral_handler, admin_only=True), True),
        ("POST", "/api/admin/free", guarded(admin_free_handler, admin_only=True), True),
        ("POST", "/api/admin/ai", guarded(admin_ai_handler, admin_only=True), True),
    )
    for method, path, handler, _admin in routes:
        app.router.add_route(method, path, handler)
        app.router.add_route("OPTIONS", path, handler)

    if WEBAPP_DIR.exists():
        # Registered last, and by hand rather than with add_static: a static mount
        # on "/" swallows every path it is asked about, and the API routes above
        # have to keep winning.
        app.router.add_get("/", static_handler)
        app.router.add_get("/{tail:.*}", static_handler)

    return app


class ApiServer:
    """Runs beside the polling loop. Never fatal: a dead API must not stop the bot."""

    def __init__(self) -> None:
        self._runner: Optional[web.AppRunner] = None

    async def start(self) -> None:
        if not API_ENABLED:
            log.info("mini app api is disabled")
            return
        try:
            runner = web.AppRunner(build_app(), access_log=None)
            await runner.setup()
            site = web.TCPSite(runner, API_HOST, API_PORT)
            await site.start()
            self._runner = runner
            log.info("mini app api listening on %s:%s (static: %s)", API_HOST, API_PORT, WEBAPP_DIR)
        except Exception:  # noqa: BLE001
            log.exception("could not start the mini app api")

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


api_server = ApiServer()
