"""HTTP API for the Telegram Mini App, the server that hosts the app itself, and
the subscription gateway on the operator's own domain.

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
``/api`` endpoint except ``/api/health`` verifies it, and the user id comes out of
the signed payload rather than out of anything the client sent separately.

Serving
-------
The same aiohttp app serves ``webapp/`` at ``/`` and the API under ``/api``. That
is deliberate: a Telegram mini app must be HTTPS, and a page on HTTPS cannot call
an HTTP API, so one origin behind one certificate is the only arrangement that
works without a second domain. Put any TLS terminator in front of it (the docs
use Caddy, two lines) and point ``WEBAPP_URL`` at it.

Two things here are not for the mini app, and they are the reason this file grew.

``/sub/...`` is the subscription gateway. A panel lives on ``workers.dev``, which
is DNS-poisoned in Iran, so a client could hold a perfectly good config and still
fail to *fetch* the subscription that carries it - which looks exactly like a dead
config and got reported as one. The gateway serves the same list from the
operator's own domain instead. It takes a signed token rather than the launch
signature, because a subscription URL is pasted into client apps that know
nothing about Telegram.

``/dl/...`` is file download. Telegram's in-app browser, and iOS most of all,
refuses a Blob download built in JavaScript: the button appeared to do nothing at
all, which is why "download config does not work" and "iPhone cannot use
WireGuard" were the same bug wearing two hats. A real URL with a real
``Content-Disposition`` is something every webview understands, and on iOS it is
what puts a ``.conf`` in front of the WireGuard app's own importer.

Long jobs
---------
Building a panel takes the better part of a minute, which is longer than a mobile
browser will hold a request open. ``/api/panel/build`` therefore returns a job id
immediately and the app polls ``/api/job/{id}`` for the same five step checklist
the bot draws in chat.
"""

from __future__ import annotations

import asyncio
import base64
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
from urllib.parse import parse_qsl, quote

from aiohttp import web

from . import (
    aipin,
    db,
    deploy,
    fragment,
    freepool,
    profiles,
    proxies,
    referral,
    shadowsocks,
    store,
    subgw,
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
# A download link is short lived on purpose: it carries a private key past the
# launch signature, so it is valid for one sitting and not for a bookmark.
DOWNLOAD_TTL = int(os.getenv("DOWNLOAD_TTL", "3600") or 3600)
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
# signed download tickets
# --------------------------------------------------------------------- #


def _ticket(tg_id: int, kind: str, platform: str = "", index: int = 0) -> str:
    """A short lived, signed description of one file to render.

    Nothing is stored: the ticket *is* the request, and the server rebuilds the
    file from the database when it is presented. That keeps a stale link from
    handing out a stale key.
    """
    payload = {
        "u": int(tg_id),
        "k": str(kind),
        "p": str(platform or ""),
        "i": int(index or 0),
        "e": int(time.time()) + DOWNLOAD_TTL,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"dl:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{body}.{base64.urlsafe_b64encode(mac[:12]).decode('ascii').rstrip('=')}"


def _read_ticket(raw: str) -> Optional[dict]:
    body, _, signature = str(raw or "").partition(".")
    if not body or not signature:
        return None
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"dl:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(base64.urlsafe_b64encode(mac[:12]).decode("ascii").rstrip("="), signature):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict) or int(payload.get("e") or 0) < int(time.time()):
        return None
    return payload


def _public_origin(request: web.Request) -> str:
    """Where a link handed to a client app should point.

    ``PUBLIC_URL`` wins, because that is the domain the operator actually owns
    and terminates TLS on. Failing that, the request's own forwarded host is used
    - which is right behind a reverse proxy and harmless in front of one.
    """
    configured = subgw.origin()
    if configured:
        return configured
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    host = forwarded_host or request.host
    scheme = forwarded_proto or request.scheme
    return f"{scheme}://{host}".rstrip("/")


def _download_url(request: web.Request, tg_id: int, kind: str, platform: str = "", index: int = 0) -> str:
    return f"{_public_origin(request)}/dl/{_ticket(tg_id, kind, platform, index)}"


def _qr_url(request: web.Request, text: str) -> str:
    return f"{_public_origin(request)}/api/qr?text={quote(text, safe='')}"


# --------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------- #


async def _lang(tg_id: int, row: Any) -> str:
    lang = str((row["lang"] if row is not None else "") or settings.default_lang).lower()
    return lang if lang in {"fa", "en"} else settings.default_lang


async def _panel_payload(tg_id: int, request: Optional[web.Request] = None) -> Optional[dict]:
    panel = await db.get_panel(tg_id)
    if panel is None:
        return None
    uuid = str(panel["uuid"])
    host = str(panel["host"])
    endpoints = list(panel.get("endpoints") or [])
    pin = await store.ai_pin(uuid)

    # Two sets of links, and the difference matters. ``direct`` is the worker's
    # own subscription, which is the freshest thing that exists but sits on
    # workers.dev. ``links`` is what the user is shown, and it prefers the
    # gateway on the operator's domain precisely because that is the one their
    # client can resolve.
    direct = {
        "sub": vless.sub_url(uuid, host),
        "raw": vless.sub_url(uuid, host, "raw"),
        "mix": vless.sub_url(uuid, host, "mix"),
        "trojan": trojan.sub_url(uuid, host),
        "clash": vless.sub_url(uuid, host, "clash"),
        "singbox": vless.sub_url(uuid, host, "singbox"),
    }
    links = dict(direct)
    if subgw.enabled():
        links.update(subgw.links(tg_id, uuid))

    payload = {
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
        "gateway": subgw.enabled(),
        "links": links,
        "direct": direct,
        "vless": vless.build_links(uuid, host, endpoints, settings.brand),
        "trojan": trojan.build_links(uuid, host, endpoints),
    }
    if shadowsocks.enabled():
        payload["ss"] = shadowsocks.build_links(uuid, host, endpoints, settings.brand)
        payload["ssPassword"] = shadowsocks.password_for(uuid)
    if request is not None:
        payload["downloads"] = {
            kind: _download_url(request, tg_id, kind)
            for kind in ("sub", "raw", "mix", "clash", "singbox", "fragment", "noise")
        }
    return payload


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
            "panel": await _panel_payload(tg_id, request),
            "warp": await _warp_payload(tg_id),
            "free": {
                "enabled": bool(free.get("enabled")),
                "servers": int(free.get("servers") or 0),
                "healthy": int(free.get("healthy") or 0),
                "protocols": list(freepool.PROTOCOLS),
                "sub": f"{_public_origin(request)}/sub/free/{_free_token(tg_id)}"
                if subgw.enabled()
                else "",
            },
            "protocols": {
                "vless": True,
                "trojan": True,
                "shadowsocks": shadowsocks.enabled(),
            },
            "gateway": {
                "enabled": subgw.enabled(),
                "origin": subgw.origin(),
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

    return _json(
        {"ok": True, "healthy": bool(result["healthy"]), "panel": await _panel_payload(tg_id, request)}
    )


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


def _render_export(panel: dict, kind: str) -> tuple[str, str]:
    """``(body, filename)`` for one panel export, by the same code the bot uses."""
    uuid, host = str(panel["uuid"]), str(panel["host"])
    endpoints = list(panel.get("endpoints") or [])
    brand = settings.brand
    kind = (kind or "clash").strip().lower()

    if kind == "clash":
        return profiles.clash(uuid, host, endpoints, brand), profiles.filename("clash", brand)
    if kind in {"singbox", "sing-box"}:
        return profiles.singbox(uuid, host, endpoints, brand), profiles.filename("singbox", brand)
    if kind == "noise":
        return profiles.xray_noise(uuid, host, endpoints, brand), profiles.filename("noise", brand)
    if kind == "fragment":
        return fragment.xray_config(uuid, host, endpoints, brand), fragment.filename(brand)
    if kind == "trojan":
        return "\n".join(trojan.build_links(uuid, host, endpoints)), "autovless-trojan.txt"
    if kind == "ss":
        return (
            "\n".join(shadowsocks.build_links(uuid, host, endpoints, brand)),
            "autovless-shadowsocks.txt",
        )
    if kind == "mix":
        rows = vless.build_links(uuid, host, endpoints, brand)
        rows += trojan.build_links(uuid, host, endpoints)
        if shadowsocks.enabled():
            rows += shadowsocks.build_links(uuid, host, endpoints, brand)
        return "\n".join(rows), "autovless-mix.txt"
    return "\n".join(vless.build_links(uuid, host, endpoints, brand)), "autovless.txt"


async def export_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Client config files, rendered by the same code the bot's buttons use.

    The body is still returned inline, because the app shows it on screen. What
    changed is ``url``: a real download link, which is the only thing Telegram's
    webview will actually save.
    """
    tg_id = user["id"]
    panel = await db.get_panel(tg_id)
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)

    kind = str(body.get("format") or request.query.get("format") or "clash").lower()
    payload, name = _render_export(panel, kind)
    return _json(
        {
            "ok": True,
            "filename": name,
            "body": payload,
            "url": _download_url(request, tg_id, kind),
        }
    )


async def links_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Every subscription URL for this user, gateway first."""
    tg_id = user["id"]
    panel = await db.get_panel(tg_id)
    if panel is None:
        return _json({"ok": False, "error": "no panel"}, status=404)
    uuid = str(panel["uuid"])
    return _json(
        {
            "ok": True,
            "gateway": subgw.enabled(),
            "links": subgw.links(tg_id, uuid) if subgw.enabled() else {},
            "direct": {
                "sub": vless.sub_url(uuid, str(panel["host"])),
                "mix": vless.sub_url(uuid, str(panel["host"]), "mix"),
            },
        }
    )


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


async def _warp_identity(tg_id: int, fresh: bool = False) -> tuple[Optional[dict], str]:
    row = await db.get_warp_user(tg_id)
    if row is None or fresh:
        try:
            identity = await warp.provision()
        except warp.WarpError as error:
            return None, str(error)
        await db.save_warp_user(tg_id, identity, [])
        return identity, ""
    return dict(row.get("identity") or {}), ""


async def _warp_endpoints(family: str) -> list[dict]:
    endpoints = await db.best_warp_endpoints(12, stable_only=True)
    if not endpoints:
        endpoints = await db.best_warp_endpoints(12, stable_only=False)
    rows = [dict(item) for item in endpoints]
    if family == "v6":
        return [item for item in rows if ":" in str(item["ip"])] or rows
    return [item for item in rows if ":" not in str(item["ip"])] or rows


async def warp_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """A real WireGuard/WARP config, rendered for the platform the app asked for.

    The Apple platforms get three extra things in this payload, and each of them
    is one of the reasons an iPhone user could not connect:

      * ``url`` - a genuine download, because a Blob is refused by the webview
      * ``qr`` - the config as a QR code, which is the WireGuard app's own
        import path and needs no file handling at all
      * ``clean``/``routes`` - an honest statement of what the file actually
        carries, so nobody goes looking for a setting that is not there
    """
    if not await db.get_flag("warp_enabled") and not settings.is_admin(user["id"]):
        return _json({"ok": False, "error": "warp is disabled"}, status=403)

    tg_id = user["id"]
    platform = normalise_platform(body.get("platform"))
    family = str(body.get("family") or "v4").lower()
    kind = str(body.get("kind") or "").lower() or None

    identity, error = await _warp_identity(tg_id, bool(body.get("fresh")))
    if identity is None:
        return _json({"ok": False, "error": error or "warp registration failed"}, status=502)

    rows = await _warp_endpoints(family)
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
            "routes": warpconf.allowed_ips(identity, platform),
            "filename": warpconf.filename(family, kind or "awg", platform),
            "conf": conf,
            "url": _download_url(request, tg_id, "warp", platform),
            "qr": _qr_url(request, conf),
            "link": warp.warp_link(identity, rows),
            "singbox": warp.singbox_json(identity, rows),
            "clash": warp.clash_yaml(identity, rows),
        }
    )


# --------------------------------------------------------------------- #
# free pool
# --------------------------------------------------------------------- #


def _free_token(tg_id: int) -> str:
    body = format(int(tg_id), "x")
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"free:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{body}.{base64.urlsafe_b64encode(mac[:12]).decode('ascii').rstrip('=')}"


def _free_token_ok(raw: str) -> bool:
    body, _, signature = str(raw or "").partition(".")
    if not body or not signature:
        return False
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"free:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    expected = base64.urlsafe_b64encode(mac[:12]).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, signature)


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
            # The worker's own subscription stays in the payload, but the link the
            # app shows is the gateway one: a free user's client cannot resolve
            # workers.dev either.
            "sub": f"{_public_origin(request)}/sub/free/{_free_token(tg_id)}"
            if subgw.enabled()
            else result["sub"],
            "direct": result["sub"],
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
            "gateway": {"enabled": subgw.enabled(), "origin": subgw.origin()},
            "shadowsocks": {"enabled": shadowsocks.enabled(), "path": shadowsocks.path()},
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
# subscription gateway
# --------------------------------------------------------------------- #


def _sub_response(body: str, content_type: str, fmt: str) -> web.Response:
    return web.Response(
        text=body,
        content_type=content_type.split(";")[0].strip(),
        charset="utf-8",
        headers=subgw.headers(fmt),
    )


async def sub_handler(request: web.Request) -> web.StreamResponse:
    """``/sub/<token>[/<format>]``: the subscription, on a domain that resolves."""
    fmt = (request.match_info.get("fmt") or "sub").lower()
    if fmt not in subgw.FORMATS:
        raise web.HTTPNotFound()

    found = await subgw.resolve(request.match_info.get("token", ""))
    if found is None:
        # 404 and nothing else. A wrong token must not reveal whether the user
        # exists, and a client that gets a 401 here shows a login prompt.
        raise web.HTTPNotFound()

    body, content_type, _name = subgw.render(found["panel"], fmt)
    return _sub_response(body, content_type, fmt)


async def free_sub_handler(request: web.Request) -> web.StreamResponse:
    """``/sub/free/<token>``: the same service for a user with no panel of their own.

    Built from the shared server the admin registered plus the current verified
    pool. There is no handshake test on this path on purpose: a subscription is
    fetched every few hours by every client that holds it, and re-probing six
    addresses per fetch would turn a refresh into a scan. The pool rows have
    already been verified by the sweep and are re-checked by the curator.
    """
    token = request.match_info.get("token", "")
    if not _free_token_ok(token):
        raise web.HTTPNotFound()

    server = await freepool.pick_server()
    if server is None:
        raise web.HTTPNotFound()

    endpoints = await vless.collect_endpoints(scanner)
    if not endpoints:
        raise web.HTTPServiceUnavailable(text="no verified endpoint right now")

    uuid = str(server["uuid"])
    host = str(server["host"])
    fmt = (request.query.get("format") or "sub").lower()
    rows = vless.build_links(uuid, host, endpoints, settings.brand)
    rows += trojan.build_links(uuid, host, endpoints)
    body = "\n".join(rows)
    if fmt != "raw":
        body = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return _sub_response(body, "text/plain", fmt)


# --------------------------------------------------------------------- #
# downloads
# --------------------------------------------------------------------- #


async def download_handler(request: web.Request) -> web.StreamResponse:
    """``/dl/<ticket>``: one file, as an attachment, for a webview that cannot Blob."""
    ticket = _read_ticket(request.match_info.get("ticket", ""))
    if ticket is None:
        raise web.HTTPNotFound()

    tg_id = int(ticket["u"])
    kind = str(ticket["k"])

    if kind == "warp":
        row = await db.get_warp_user(tg_id)
        if row is None:
            raise web.HTTPNotFound()
        identity = dict(row.get("identity") or {})
        platform = normalise_platform(ticket.get("p"))
        rows = [dict(item) for item in (row.get("endpoints") or [])]
        if not rows:
            rows = await _warp_endpoints("v4")
        body = warpconf.conf_for(
            identity,
            rows,
            platform=platform,
            profile=warp.obfuscation(identity.get("private_key", "")),
            index=int(ticket.get("i") or 0),
        )
        name = warpconf.filename("", "conf", platform)
    else:
        panel = await db.get_panel(tg_id)
        if panel is None:
            raise web.HTTPNotFound()
        body, name = _render_export(panel, kind)

    return web.Response(
        body=body.encode("utf-8"),
        headers={
            # octet-stream, not text/plain: a webview that recognises the type
            # renders it in a tab instead of handing it to the OS, and on iOS
            # that is the difference between importing a tunnel and staring at
            # a wall of text.
            "content-type": "application/octet-stream",
            "content-disposition": f'attachment; filename="{name}"',
            "cache-control": "no-store",
            "access-control-allow-origin": "*",
        },
    )


# --------------------------------------------------------------------- #
# qr
# --------------------------------------------------------------------- #


async def qr_handler(request: web.Request) -> web.StreamResponse:
    """A PNG for any text, so the app never needs a QR library of its own.

    The limit is generous because a WireGuard config is the whole point: the
    WireGuard app imports a tunnel from a QR code, which is the one path on iOS
    that needs no file handling at all, and a config runs to a few hundred bytes.
    """
    text = request.query.get("text", "").strip()
    if not text or len(text) > 2900:
        return _json({"ok": False, "error": "bad text"}, status=400)
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M
    except ImportError:
        return _json({"ok": False, "error": "qrcode is not installed"}, status=501)

    # A long payload only fits at the lower correction level, and a QR a phone
    # cannot fit on screen is no use either, so the box shrinks as the text grows.
    long_text = len(text) > 700
    image = qrcode.QRCode(
        error_correction=ERROR_CORRECT_L if long_text else ERROR_CORRECT_M,
        box_size=4 if long_text else 8,
        border=2,
    )
    image.add_data(text)
    buffer = io.BytesIO()
    image.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return web.Response(
        body=buffer.getvalue(),
        content_type="image/png",
        headers={"cache-control": "no-store", "access-control-allow-origin": "*"},
    )


# --------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------- #

_ASSET_STAMP: dict[str, str] = {}


def _stamp(name: str) -> str:
    """A cache-busting stamp for one asset, from its own mtime and size.

    Telegram's webview caches ``app.css`` and ``app.js`` across launches, and the
    old page carried a hand-written ``?v=2``. Every release therefore depended on
    somebody remembering to bump a number in a file they were not editing, and
    when they did not, users ran new markup against old script. The stamp is
    computed here instead, so it cannot be forgotten.
    """
    target = WEBAPP_DIR / name
    try:
        info = target.stat()
    except OSError:
        return "0"
    key = f"{name}:{int(info.st_mtime)}:{info.st_size}"
    cached = _ASSET_STAMP.get(key)
    if cached is None:
        cached = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        _ASSET_STAMP.clear()
        _ASSET_STAMP[key] = cached
    return cached


def _index_html() -> str:
    raw = (WEBAPP_DIR / "index.html").read_text(encoding="utf-8")
    return raw.replace("app.css?v=dev", f"app.css?v={_stamp('app.css')}").replace(
        "app.js?v=dev", f"app.js?v={_stamp('app.js')}"
    )


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

    if target.name == "index.html":
        return web.Response(
            text=_index_html(),
            content_type="text/html",
            charset="utf-8",
            headers={"cache-control": "no-store"},
        )
    # Everything else is fingerprinted in the markup above, so it can be cached
    # hard without ever going stale.
    cache = "public, max-age=31536000, immutable" if request.query.get("v") else "no-cache"
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
    return _json(
        {
            "ok": True,
            "brand": settings.brand,
            "webapp": WEBAPP_DIR.exists(),
            "gateway": subgw.enabled(),
            "origin": subgw.origin(),
            "shadowsocks": shadowsocks.enabled(),
        }
    )


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors])
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/qr", qr_handler)

    # Public, token-authenticated routes. Registered before the static catch-all
    # for the same reason the API routes are: a mount on "/" answers everything.
    app.router.add_get("/sub/free/{token}", free_sub_handler)
    app.router.add_get("/sub/{token}", sub_handler)
    app.router.add_get("/sub/{token}/{fmt}", sub_handler)
    app.router.add_get("/dl/{ticket}", download_handler)

    routes = (
        ("POST", "/api/state", guarded(state_handler), False),
        ("POST", "/api/settings", guarded(settings_handler), False),
        ("POST", "/api/panel/build", guarded(build_handler), False),
        ("GET", "/api/job/{job}", guarded(job_handler), False),
        ("POST", "/api/panel/apply", guarded(apply_handler), False),
        ("POST", "/api/panel/delete", guarded(delete_handler), False),
        ("POST", "/api/panel/export", guarded(export_handler), False),
        ("POST", "/api/panel/links", guarded(links_handler), False),
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
            log.info(
                "api listening on %s:%s (static: %s, gateway: %s)",
                API_HOST,
                API_PORT,
                WEBAPP_DIR,
                subgw.origin() or "off",
            )
        except Exception:  # noqa: BLE001
            log.exception("could not start the mini app api")

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


api_server = ApiServer()
