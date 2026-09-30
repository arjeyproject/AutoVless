"""HTTP API for the Telegram Mini App, the server that hosts the app itself, the
subscription gateway on the operator's own domain, and the payment callback.

Trust
-----
Telegram signs every mini app launch. ``initData`` arrives with an HMAC computed
under a key derived from the bot token, so verifying it proves the caller is the
Telegram user it claims to be. Every ``/api`` endpoint except ``/api/health``
verifies it, and the user id comes out of the signed payload.

Serving
-------
The same aiohttp app serves ``webapp/`` at ``/`` and the API under ``/api``: a
Telegram mini app must be HTTPS, and a page on HTTPS cannot call an HTTP API, so
one origin behind one certificate is the arrangement that works. Put any TLS
terminator in front of it (the install guide uses Caddy) and point
``WEBAPP_URL`` / ``PUBLIC_URL`` at it.

Public routes that are not for the mini app
------------------------------------------
``/sub/...`` is the subscription gateway (``workers.dev`` is DNS-poisoned in
Iran, so subscriptions are served from the operator's domain). ``/dl/...`` is
file download, because Telegram's webview refuses Blob downloads.
``/pay/zarinpal/callback`` is where Zarinpal sends the user back after paying;
the payment is verified server-to-server there and the user unlocked.

Long jobs
---------
Building a panel takes the better part of a minute, so ``/api/panel/build``
returns a job id and the app polls ``/api/job/{id}``. A job belongs to the user
who started it and nobody else can read it: the finished job carries the panel.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
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
    payment,
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
from .i18n import t
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
# A full clean-IP sweep is expensive on a small box; users get one per window.
RESCAN_COOLDOWN = 120
APPLE = {"ios", "macos"}

_jobs: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()
_rescans: dict[int, float] = {}


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

# Reachable even when the invite lock or the paywall is closed: these are what a
# locked user needs to see, and to use, to get unlocked.
OPEN_WHILE_LOCKED = {"/api/state", "/api/settings", "/api/referral", "/api/health", "/api/pay/start"}


def guarded(handler: Handler, admin_only: bool = False) -> Callable:
    """Verify the launch signature, then hand the handler the user and the body."""

    async def wrapper(request: web.Request) -> web.StreamResponse:
        body = await _body(request)
        user = verify_init_data(_init_data(request, body))
        if user is None:
            return _json({"ok": False, "error": "unauthorised"}, status=401)

        tg_id = int(user["id"])
        is_admin = settings.is_admin(tg_id)
        row = await db.upsert_user(tg_id, user.get("username"), user.get("first_name"))
        if row["is_banned"] and not is_admin:
            return _json({"ok": False, "error": "banned"}, status=403)
        if admin_only and not is_admin:
            return _json({"ok": False, "error": "admins only"}, status=403)

        # The invite lock and the paywall apply here too, or the mini app would be
        # a way around them.
        if request.path not in OPEN_WHILE_LOCKED:
            if not await referral.unlocked(tg_id, is_admin):
                return _json(
                    {
                        "ok": False,
                        "error": "locked",
                        "required": await referral.required(),
                        "invited": await referral.invited(tg_id),
                    },
                    status=403,
                )
            if not await payment.is_paid(tg_id, is_admin):
                return _json(
                    {
                        "ok": False,
                        "error": "payment_required",
                        "payment": await payment.public_state(tg_id, is_admin),
                    },
                    status=402,
                )

        try:
            return await handler(request, body, {"id": tg_id, "row": row, "raw": user})
        except web.HTTPException:
            raise
        except Exception as error:  # noqa: BLE001
            log.exception("api handler failed: %s", request.path)
            return _json({"ok": False, "error": str(error)[:200]}, status=500)

    return wrapper


# --------------------------------------------------------------------- #
# signed download tickets
# --------------------------------------------------------------------- #


def _ticket(tg_id: int, kind: str, platform: str = "", index: int = 0) -> str:
    """A short lived, signed description of one file to render."""
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
    """Where a link handed to a client app should point."""
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

    direct = {
        "sub": vless.sub_url(uuid, host),
        "raw": vless.sub_url(uuid, host, "raw"),
        "mix": vless.sub_url(uuid, host, "mix"),
        "trojan": trojan.sub_url(uuid, host),
        "clash": vless.sub_url(uuid, host, "clash"),
        "singbox": vless.sub_url(uuid, host, "singbox"),
    }
    if shadowsocks.enabled():
        direct["ss"] = shadowsocks.sub_url(uuid, host)
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
    identity = dict((row or {}).get("identity") or {})
    payload = {
        "hasIdentity": row is not None,
        # The account type lives on the identity, not on the row. Reading it off
        # the row made every WARP+ user show up as "free".
        "accountType": str(identity.get("account_type") or "free"),
        "endpoints": [dict(item) for item in endpoints],
        "platforms": list(PLATFORM_ORDER),
    }
    if row is not None:
        payload["addresses"] = {"v4": identity.get("v4"), "v6": identity.get("v6")}
        payload["refreshes"] = int(row.get("refreshes") or 0)
    return payload


async def state_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    tg_id = user["id"]
    row = user["row"]
    is_admin = settings.is_admin(tg_id)
    lang = await _lang(tg_id, row)
    pool = await db.pool_stats()
    relays = await proxy_scanner.stats()
    warp_pool = await db.warp_pool_stats()
    free = await freepool.stats()
    goal = await referral.required()
    invited = await referral.invited(tg_id)
    unlocked = await referral.unlocked(tg_id, is_admin)
    pay = await payment.public_state(tg_id, is_admin)
    # A locked or unpaid user gets the shell of the app and the way to unlock it,
    # not the panel and its credentials.
    open_ = unlocked and pay["paid"]

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
                "isAdmin": is_admin,
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
            "panel": await _panel_payload(tg_id, request) if open_ else None,
            "warp": await _warp_payload(tg_id),
            "free": {
                "enabled": bool(free.get("enabled")),
                "servers": int(free.get("servers") or 0),
                "healthy": int(free.get("healthy") or 0),
                "protocols": list(freepool.PROTOCOLS),
                "sub": f"{_public_origin(request)}/sub/free/{_free_token(tg_id)}"
                if subgw.enabled() and open_
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
                "unlocked": unlocked,
                "link": referral.link(referral.cached_username(), tg_id),
            },
            "payment": pay,
            "bot": referral.cached_username(),
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
# payment
# --------------------------------------------------------------------- #


async def pay_start_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Open a payment from the mini app: a Zarinpal URL or a Stars invoice link."""
    tg_id = user["id"]
    lang = await _lang(tg_id, user["row"])
    gateway = str(body.get("gateway") or "").lower()
    try:
        if gateway == "zarinpal":
            url = await payment.zarinpal_start(tg_id)
            return _json({"ok": True, "gateway": "zarinpal", "url": url})
        if gateway == "stars":
            from .handlers.payment import period

            cfg = await payment.config()
            link = await payment.stars_invoice_link(
                title=t(lang, "pay.stars_title", brand=settings.brand),
                description=t(
                    lang, "pay.stars_desc", brand=settings.brand, period=period(cfg["days"], lang)
                ),
                label=t(lang, "pay.stars_label"),
                tg_id=tg_id,
            )
            return _json({"ok": True, "gateway": "stars", "url": link})
    except payment.PaymentError as error:
        return _json({"ok": False, "error": str(error)}, status=400)
    return _json({"ok": False, "error": "unknown gateway"}, status=400)


def _pay_page(ok: bool, ref: str, lang: str) -> str:
    """The page Zarinpal lands the user on. Self-contained, RTL-aware."""
    username = referral.cached_username()
    back = f"https://t.me/{username}" if username else "https://t.me"
    fa = lang != "en"
    title = (
        ("پرداخت موفق بود" if ok else "پرداخت انجام نشد")
        if fa
        else ("Payment successful" if ok else "Payment not completed")
    )
    text = (
        (
            "اشتراک تو فعال شد. به ربات برگرد؛ همه‌چیز باز است."
            if ok
            else "اگر مبلغی از حسابت کم شده، ظرف ۷۲ ساعت به حسابت برمی‌گردد. دوباره از داخل ربات تلاش کن."
        )
        if fa
        else (
            "Your access is active. Head back to the bot."
            if ok
            else "If money left your account it is refunded within 72 hours. Please try again from the bot."
        )
    )
    button = "بازگشت به ربات" if fa else "Back to the bot"
    reference = (
        f'<p class="ref">{"کد پیگیری" if fa else "Reference"}: <b>{html.escape(ref)}</b></p>'
        if ok and ref
        else ""
    )
    color = "#21d4a8" if ok else "#ff5d6c"
    mark = "\u2713" if ok else "\u2715"
    return f"""<!doctype html><html lang="{'fa' if fa else 'en'}" dir="{'rtl' if fa else 'ltr'}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(settings.brand)}</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Vazirmatn,system-ui,sans-serif;
background:radial-gradient(circle at 20% 10%,#1d2b55,#080b14 60%);color:#eef2ff}}
.card{{width:min(92vw,380px);padding:32px 24px;border-radius:24px;text-align:center;
background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(20px)}}
.mark{{width:72px;height:72px;margin:0 auto 16px;border-radius:50%;display:grid;place-items:center;
font-size:36px;color:#fff;background:{color};box-shadow:0 12px 40px -8px {color}}}
h1{{font-size:20px;margin:0 0 10px}}p{{line-height:1.8;color:#b8c2de;font-size:14px}}
.ref b{{color:#fff;direction:ltr;display:inline-block}}
a{{display:block;margin-top:18px;padding:14px;border-radius:14px;color:#fff;text-decoration:none;
font-weight:700;background:linear-gradient(135deg,#5b8cff,#21d4a8)}}
</style></head><body><div class="card"><div class="mark">{mark}</div><h1>{title}</h1>
<p>{text}</p>{reference}<a href="{html.escape(back)}">{button}</a></div></body></html>"""


async def zarinpal_callback(request: web.Request) -> web.StreamResponse:
    """``/pay/zarinpal/callback?Authority=...&Status=OK|NOK``."""
    authority = request.query.get("Authority", "")
    status = request.query.get("Status", "")
    result = await payment.zarinpal_verify(authority, status)

    lang = settings.default_lang
    if result.get("tg_id"):
        row = await db.get_user(int(result["tg_id"]))
        lang = str((row["lang"] if row is not None else "") or lang)

    if result.get("ok") and not result.get("again"):
        from .handlers.payment import notify_paid

        await notify_paid(int(result["tg_id"]), str(result.get("ref") or ""), int(result.get("expires") or 0))

    return web.Response(
        text=_pay_page(bool(result.get("ok")), str(result.get("ref") or ""), lang),
        content_type="text/html",
        charset="utf-8",
        headers={"cache-control": "no-store"},
    )


PAY_KEYS = {
    "amount": ("pay_amount", 1000, 1_000_000_000),
    "stars": ("pay_stars", 1, 100_000),
    "days": ("pay_days", 0, 3650),
}


async def admin_pay_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Read or change the payment settings. The merchant id is never echoed back."""
    action = str(body.get("action") or "get")
    if action == "set":
        key = str(body.get("key") or "")
        value = body.get("value")
        if key in PAY_KEYS:
            option, low, high = PAY_KEYS[key]
            try:
                number = int(str(value).strip())
            except (TypeError, ValueError):
                return _json({"ok": False, "error": "not a number"}, status=400)
            if not low <= number <= high:
                return _json({"ok": False, "error": "out of range"}, status=400)
            await payment.put(option, number)
        elif key == "gateway":
            if str(value) not in payment.GATEWAYS:
                return _json({"ok": False, "error": "unknown gateway"}, status=400)
            await payment.put("pay_gateway", str(value))
        elif key in {"enabled", "sandbox"}:
            await payment.put(f"pay_{key}", "1" if value in {True, 1, "1", "true", "on"} else "0")
        elif key == "merchant":
            from .handlers.payment import MERCHANT_RE

            raw = str(value or "").strip()
            if raw and not MERCHANT_RE.match(raw):
                return _json({"ok": False, "error": "bad merchant id"}, status=400)
            await payment.put("pay_merchant", raw)
        else:
            return _json({"ok": False, "error": "unknown option"}, status=400)
        await db.log_event("option", user["id"], f"pay {key}")

    cfg = await payment.config()
    cfg["merchant"] = bool(cfg["merchant"])
    return _json(
        {
            "ok": True,
            "config": cfg,
            "stats": await payment.stats(),
            "callback": payment.callback_url(),
        }
    )


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #


def _new_job(kind: str, owner: int) -> str:
    _reap_jobs()
    job_id = secrets.token_urlsafe(12)
    _jobs[job_id] = {"kind": kind, "state": "running", "step": 0, "at": time.time(), "owner": int(owner)}
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
        job.update({"state": "failed", "error": str(error)[:200], "at": time.time()})
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

    # One build at a time per user: a double tap used to start two deploys that
    # raced each other onto the same Cloudflare account.
    for job in _jobs.values():
        if job.get("owner") == tg_id and job.get("state") == "running":
            return _json({"ok": False, "error": "a build is already running"}, status=409)

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

    job_id = _new_job("build", tg_id)
    _spawn(_run_build(job_id, tg_id, token, reuse), f"api-build-{tg_id}")
    return _json({"ok": True, "job": job_id, "steps": list(deploy.STEP_KEYS)})


async def job_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    job = _jobs.get(request.match_info.get("job", ""))
    # Somebody else's job is reported as unknown, exactly like a job that does not
    # exist: a finished job carries the owner's panel and its uuid.
    if job is None or int(job.get("owner") or 0) != int(user["id"]):
        return _json({"ok": False, "error": "unknown job"}, status=404)
    return _json(
        {"ok": True, "job": {key: value for key, value in job.items() if key not in {"at", "owner"}}}
    )


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
        rows += shadowsocks.build_links(uuid, host, endpoints, brand)
        return "\n".join(rows), "autovless-mix.txt"
    return "\n".join(vless.build_links(uuid, host, endpoints, brand)), "autovless.txt"


async def export_handler(request: web.Request, body: dict, user: dict) -> web.StreamResponse:
    """Client config files, with a real download URL the webview can save."""
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
    """A clean-IP sweep. Rate limited: it used to be one tap per full scan, for anyone."""
    tg_id = user["id"]
    if not settings.is_admin(tg_id):
        now = time.monotonic()
        last = _rescans.get(tg_id, 0.0)
        if now - last < RESCAN_COOLDOWN:
            return _json(
                {"ok": False, "error": "cooldown", "wait": int(RESCAN_COOLDOWN - (now - last))},
                status=429,
            )
        _rescans[tg_id] = now
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

    Apple platforms get the AmneziaWG-app file as well (``awg``, with its own
    download link and QR) and Hiddify links: the clean file alone loads on an
    iPhone and then carries nothing on a filtered carrier.
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
    ordered = warpconf.order_for(rows, platform)

    payload = {
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
        "hiddify": warp.hiddify_link(identity, ordered or rows, name=f"{settings.brand}-WARP"),
        "hiddifyAuto": warp.hiddify_auto_link(),
        "singbox": warp.singbox_json(identity, rows),
        "clash": warp.clash_yaml(identity, rows),
    }
    if platform in APPLE:
        awg = warpconf.apple_amnezia_conf(identity, rows, profile, platform=platform)
        payload.update(
            {
                "awg": awg,
                "awgFilename": warpconf.filename(family, "amnezia", platform),
                "awgUrl": _download_url(request, tg_id, "warpawg", platform),
                "awgQr": _qr_url(request, awg),
            }
        )
    return _json(payload)


# --------------------------------------------------------------------- #
# free pool
# --------------------------------------------------------------------- #


def _free_token(tg_id: int) -> str:
    body = format(int(tg_id), "x")
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"free:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{body}.{base64.urlsafe_b64encode(mac[:12]).decode('ascii').rstrip('=')}"


def _free_token_user(raw: str) -> Optional[int]:
    body, _, signature = str(raw or "").partition(".")
    if not body or not signature:
        return None
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), f"free:{body}".encode("utf-8"), hashlib.sha256
    ).digest()
    expected = base64.urlsafe_b64encode(mac[:12]).decode("ascii").rstrip("=")
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        return int(body, 16)
    except ValueError:
        return None


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
    cfg = await payment.config()
    cfg["merchant"] = bool(cfg["merchant"])
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
            "payment": {"config": cfg, "stats": await payment.stats(), "callback": payment.callback_url()},
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
        raise web.HTTPNotFound()
    # A subscription is the product. A lapsed subscriber's client keeps fetching
    # it, so the paywall has to apply here too or payment would be optional.
    if not await payment.is_paid(int(found["tg_id"])):
        raise web.HTTPNotFound()

    body, content_type, _name = subgw.render(found["panel"], fmt)
    return _sub_response(body, content_type, fmt)


async def free_sub_handler(request: web.Request) -> web.StreamResponse:
    """``/sub/free/<token>``: the same service for a user with no panel of their own."""
    tg_id = _free_token_user(request.match_info.get("token", ""))
    if tg_id is None or not await payment.is_paid(tg_id):
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

    if kind in {"warp", "warpawg"}:
        row = await db.get_warp_user(tg_id)
        if row is None:
            raise web.HTTPNotFound()
        identity = dict(row.get("identity") or {})
        platform = normalise_platform(ticket.get("p"))
        rows = [dict(item) for item in (row.get("endpoints") or [])]
        if not rows:
            rows = await _warp_endpoints("v4")
        profile = warp.obfuscation(identity.get("private_key", ""))
        if kind == "warpawg":
            body = warpconf.apple_amnezia_conf(
                identity, rows, profile, platform=platform, index=int(ticket.get("i") or 0)
            )
            name = warpconf.filename("", "amnezia", platform)
        else:
            body = warpconf.conf_for(
                identity, rows, platform=platform, profile=profile, index=int(ticket.get("i") or 0)
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
            # octet-stream, not text/plain: on iOS that is the difference between
            # importing a tunnel and staring at a wall of text.
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
    """A PNG for any text, so the app never needs a QR library of its own."""
    text = request.query.get("text", "").strip()
    if not text or len(text) > 2900:
        return _json({"ok": False, "error": "bad text"}, status=400)
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M
    except ImportError:
        return _json({"ok": False, "error": "qrcode is not installed"}, status=501)

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
    """A cache-busting stamp for one asset, from its own mtime and size."""
    target = WEBAPP_DIR / name
    try:
        info = target.stat()
    except OSError:
        return "0"
    key = f"{name}:{int(info.st_mtime)}:{info.st_size}"
    cached = _ASSET_STAMP.get(key)
    if cached is None:
        cached = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
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
            "payment": bool(await payment.enabled()),
        }
    )


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors])
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/qr", qr_handler)

    # Public, token-authenticated routes. Registered before the static catch-all.
    app.router.add_get("/sub/free/{token}", free_sub_handler)
    app.router.add_get("/sub/{token}", sub_handler)
    app.router.add_get("/sub/{token}/{fmt}", sub_handler)
    app.router.add_get("/dl/{ticket}", download_handler)
    app.router.add_get("/pay/zarinpal/callback", zarinpal_callback)

    routes = (
        ("POST", "/api/state", guarded(state_handler)),
        ("POST", "/api/settings", guarded(settings_handler)),
        ("POST", "/api/pay/start", guarded(pay_start_handler)),
        ("POST", "/api/panel/build", guarded(build_handler)),
        ("GET", "/api/job/{job}", guarded(job_handler)),
        ("POST", "/api/panel/apply", guarded(apply_handler)),
        ("POST", "/api/panel/delete", guarded(delete_handler)),
        ("POST", "/api/panel/export", guarded(export_handler)),
        ("POST", "/api/panel/links", guarded(links_handler)),
        ("POST", "/api/panel/ping", guarded(ping_handler)),
        ("POST", "/api/rescan", guarded(rescan_handler)),
        ("POST", "/api/warp/build", guarded(warp_handler)),
        ("POST", "/api/free/build", guarded(free_handler)),
        ("POST", "/api/referral", guarded(referral_handler)),
        ("POST", "/api/admin/state", guarded(admin_state_handler, admin_only=True)),
        ("POST", "/api/admin/flag", guarded(admin_flag_handler, admin_only=True)),
        ("POST", "/api/admin/referral", guarded(admin_referral_handler, admin_only=True)),
        ("POST", "/api/admin/free", guarded(admin_free_handler, admin_only=True)),
        ("POST", "/api/admin/ai", guarded(admin_ai_handler, admin_only=True)),
        ("POST", "/api/admin/pay", guarded(admin_pay_handler, admin_only=True)),
    )
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)
        app.router.add_route("OPTIONS", path, handler)

    if WEBAPP_DIR.exists():
        # Registered last, and by hand rather than with add_static: a static mount
        # on "/" swallows every path it is asked about.
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
