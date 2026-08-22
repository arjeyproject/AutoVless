"""Payload and URL builder for the Telegram Mini App served from webapp/.

The mini app is a static page on GitHub Pages. It cannot read the database, so
everything it needs is packed into one base64url blob and handed over in the
query string when the Web App button is built.

Every engine read here is best effort on purpose: a missing scanner, a stopped
autopilot or a WARP module that moved must never stop the mini app from opening.
"""

from __future__ import annotations

import base64
import importlib
import inspect
import json
import logging
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from . import db, vless
from .config import settings

log = logging.getLogger("autovless.webapp")

# The payload rides in a URL, so it stays small on purpose.
MAX_ENDPOINTS = 8
MAX_LINKS = 8
MAX_WARP_ENDPOINTS = 6


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _member(module: str, attr: str) -> Any:
    try:
        loaded = importlib.import_module(f".{module}", __package__)
    except Exception:
        return None
    return getattr(loaded, attr, None)


async def _stats(module: str, attr: str) -> dict:
    target = _member(module, attr)
    if target is None:
        return {}
    fn = getattr(target, "stats", None)
    if fn is None:
        return {}
    try:
        return dict(await _maybe_await(fn()) or {})
    except Exception:
        log.debug("stats read failed for %s.%s", module, attr, exc_info=True)
        return {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _warp_profile(private_key: str) -> dict:
    if not private_key:
        return {}
    fn = _member("warp", "obfuscation")
    if fn is None:
        return {}
    try:
        return dict(fn(private_key) or {})
    except Exception:
        log.debug("warp obfuscation profile failed", exc_info=True)
        return {}


async def _warp_fallback_endpoints() -> list[dict]:
    try:
        rows = await db.best_warp_endpoints(MAX_WARP_ENDPOINTS, stable_only=True)
        if not rows:
            rows = await db.best_warp_endpoints(MAX_WARP_ENDPOINTS, stable_only=False)
        return [dict(row) for row in rows]
    except Exception:
        return []


async def build_payload(tg_id: int, lang: str) -> dict:
    """Everything the mini app renders on first paint."""
    lang = "en" if str(lang).lower() == "en" else "fa"

    try:
        panel = await db.get_panel(tg_id)
    except Exception:
        panel = None
    try:
        warp_user = await db.get_warp_user(tg_id)
    except Exception:
        warp_user = None
    try:
        pool = await db.pool_stats()
    except Exception:
        pool = {}

    relays = await _stats("proxies", "proxy_scanner") or await _stats("scanner", "proxy_scanner")
    warp_stats = await _stats("warpscan", "warp_scanner")
    pilot = await _stats("autopilot", "autopilot")
    scanner = _member("scanner", "scanner")

    payload: dict = {
        "version": 1,
        "lang": lang,
        "brand": settings.brand,
        "stats": {
            "cleanPool": {
                "total": _int(pool.get("total")),
                "verified": _int(pool.get("verified")),
                "domains": _int(pool.get("domains")),
                "best": pool.get("best"),
                "updatedAt": _int(pool.get("updated_at")),
                "history": [],
            },
            "relays": {
                "total": _int(relays.get("total")),
                "verified": _int(relays.get("verified")),
            },
            "warp": {
                "stable": _int(warp_stats.get("stable")),
                "total": _int(warp_stats.get("total")),
                "best": warp_stats.get("best"),
                "ports": list(warp_stats.get("ports") or settings.warp_ports or []),
                "updatedAt": _int(warp_stats.get("updated_at")),
            },
            "scanner": {
                "active": bool(pilot.get("enabled", settings.autopilot)),
                "ports": list(getattr(scanner, "ports", settings.all_ports) or []),
            },
        },
        "settings": {
            "tlsPorts": list(settings.tls_ports),
            "httpPorts": list(settings.http_ports),
            "tlsCount": int(settings.tls_config_count),
            "httpCount": int(settings.http_config_count),
            "storeTokens": bool(settings.store_tokens),
        },
        "bot": {},
    }

    if panel:
        host = str(panel.get("host") or "")
        uuid = str(panel.get("uuid") or "")
        endpoints = list(panel.get("endpoints") or [])[:MAX_ENDPOINTS]
        payload["panel"] = {
            "uuid": uuid,
            "host": host,
            "build": str(panel.get("rebuilds") or 0),
            "tokenStored": bool(panel.get("token")),
            "links": {
                "sub": vless.sub_url(uuid, host),
                "raw": vless.sub_url(uuid, host, "raw"),
                "clash": vless.sub_url(uuid, host, "clash"),
                "singbox": vless.sub_url(uuid, host, "singbox"),
            },
            "endpoints": endpoints,
            "linksRaw": [],
        }
        try:
            links = vless.build_links(uuid, host, endpoints, settings.brand)
            payload["panel"]["linksRaw"] = links[:MAX_LINKS]
        except Exception:
            log.debug("link rebuild for mini app failed", exc_info=True)

    if warp_user:
        identity = dict(warp_user.get("identity") or {})
        payload["warp"] = {
            "identity": identity,
            "endpoints": list(warp_user.get("endpoints") or [])[:MAX_WARP_ENDPOINTS],
            "profile": _warp_profile(str(identity.get("private_key") or "")),
        }
    else:
        payload["warp"] = {
            "identity": {},
            "endpoints": await _warp_fallback_endpoints(),
            "profile": {},
        }

    return payload


def encode_payload(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _b64url(raw)


async def build_webapp_url(tg_id: int, lang: str) -> str:
    """Mini app URL with the payload in the query string.

    The fragment is left alone: Telegram writes its own tgWebAppData there.
    """
    base = settings.webapp_url.strip()
    if not base:
        raise RuntimeError("WEBAPP_URL is not configured")

    payload = await build_payload(tg_id, lang)
    token = encode_payload(payload)

    parts = list(urlsplit(base if base.endswith("/") else base + "/"))
    parts[3] = urlencode({"payload": token})
    parts[4] = ""
    return urlunsplit(parts)
