"""Subscription gateway on the operator's own domain.

The problem this closes
-----------------------
Every subscription link the bot handed out pointed at the panel itself, and a
panel lives at ``<script>.<subdomain>.workers.dev``. That hostname is resolvable
almost everywhere and not in Iran, where ``workers.dev`` is DNS-poisoned wholesale
- so the *tunnel* worked while the *subscription* did not. The user imported a
link, the client tried to fetch it, got nothing, and showed an empty profile. It
reads exactly like a dead config, which is why it was reported as one.

The fix is to stop asking the client to reach ``workers.dev`` at all. The bot
already runs an HTTPS origin for the mini app, on a domain the operator owns, so
the subscription is served from there: the gateway reads the endpoint list out of
the database - the same list the autopilot keeps fresh - and renders it on
request. Nothing is cached and nothing is stored, so a client refresh picks up
whatever the last scan produced, which is the behaviour the worker-hosted
subscription had.

Tokens
------
A subscription URL is handed to client apps and lands in logs, so it must not
contain the account uuid, and it must not be guessable. Each one is
``<user-in-base36>.<hmac>``: the id is there so the gateway knows whose panel to
render, and the signature covers the id *and* the panel uuid under the instance
secret. That last part is what makes the link self-revoking - delete the panel,
build a new one, and every old link stops verifying, because the uuid it was
signed against is gone.

Nothing here trusts the token beyond identifying a row. There is no write path in
this module at all.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional

from . import db, fragment, profiles, shadowsocks, trojan, vless
from .config import settings

log = logging.getLogger("autovless.subgw")

# What ``/sub/<token>/<format>`` accepts. ``sub`` is the bare path.
FORMATS = (
    "sub",
    "raw",
    "mix",
    "trojan",
    "ss",
    "clash",
    "singbox",
    "fragment",
    "noise",
    "all",
)


def origin() -> str:
    """The HTTPS origin subscriptions are served from.

    ``PUBLIC_URL`` is the operator's own domain and the only value that should be
    here. ``WEBAPP_URL`` is accepted as a fallback because a working mini app
    already proves that origin is reachable over HTTPS, which is exactly the
    property a subscription needs - so an operator who has set one and not the
    other still gets working links instead of silence.
    """
    raw = (os.getenv("PUBLIC_URL") or os.getenv("WEBAPP_URL") or "").strip()
    if raw and not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def enabled() -> bool:
    return bool(origin())


# --------------------------------------------------------------------- #
# tokens
# --------------------------------------------------------------------- #


def _sign(body: str, uuid: str) -> str:
    mac = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"sub:{body}:{uuid}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(mac[:12]).decode("ascii").rstrip("=")


def token(tg_id: int, uuid: str) -> str:
    body = format(int(tg_id), "x")
    return f"{body}.{_sign(body, uuid)}"


def parse(raw: str) -> Optional[int]:
    """The user id inside a token, shape-checked only.

    The signature cannot be verified here, because verifying it needs the panel
    uuid and finding the panel needs the id. ``resolve`` does both.
    """
    body, _, signature = str(raw or "").strip().partition(".")
    if not body or not signature:
        return None
    try:
        return int(body, 16)
    except ValueError:
        return None


async def resolve(raw: str) -> Optional[dict]:
    """The panel a token points at, or ``None`` when it does not verify."""
    tg_id = parse(raw)
    if tg_id is None:
        return None
    try:
        panel = await db.get_panel(tg_id)
    except Exception:  # noqa: BLE001
        log.debug("panel lookup failed for a subscription token", exc_info=True)
        return None
    if panel is None:
        return None

    body = str(raw).partition(".")[0]
    expected = _sign(body, str(panel["uuid"]))
    if not hmac.compare_digest(expected, str(raw).partition(".")[2]):
        return None
    return {"tg_id": tg_id, "panel": panel}


def link(tg_id: int, uuid: str, fmt: str = "") -> str:
    """The public subscription URL for this panel."""
    base = f"{origin()}/sub/{token(tg_id, uuid)}"
    return f"{base}/{fmt}" if fmt and fmt != "sub" else base


def links(tg_id: int, uuid: str) -> dict[str, str]:
    """Every format, ready for the mini app and the bot keyboards."""
    return {name: link(tg_id, uuid, name) for name in FORMATS}


# --------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------- #


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def render(panel: dict, fmt: str = "sub") -> tuple[str, str, str]:
    """``(body, content type, filename)`` for one subscription format.

    The endpoint list comes from the panel row, which the autopilot rewrites every
    time it applies fresh addresses, so this is never a frozen snapshot.
    """
    fmt = (fmt or "sub").strip().lower()
    uuid = str(panel["uuid"])
    host = str(panel["host"])
    endpoints = list(panel.get("endpoints") or [])
    brand = settings.brand

    plain = "text/plain; charset=utf-8"

    if fmt == "clash":
        return profiles.clash(uuid, host, endpoints, brand), "text/yaml; charset=utf-8", \
            profiles.filename("clash", brand)
    if fmt == "singbox":
        return profiles.singbox(uuid, host, endpoints, brand), "application/json; charset=utf-8", \
            profiles.filename("singbox", brand)
    if fmt == "noise":
        return profiles.xray_noise(uuid, host, endpoints, brand), "application/json; charset=utf-8", \
            profiles.filename("noise", brand)
    if fmt == "fragment":
        return fragment.xray_config(uuid, host, endpoints, brand), \
            "application/json; charset=utf-8", fragment.filename(brand)

    if fmt == "trojan":
        body = "\n".join(trojan.build_links(uuid, host, endpoints, brand))
    elif fmt == "ss":
        body = "\n".join(shadowsocks.build_links(uuid, host, endpoints, brand))
    elif fmt in {"mix", "all"}:
        rows = vless.build_links(uuid, host, endpoints, brand)
        rows += trojan.build_links(uuid, host, endpoints, brand)
        if shadowsocks.enabled():
            rows += shadowsocks.build_links(uuid, host, endpoints, brand)
        body = "\n".join(rows)
    else:
        body = "\n".join(vless.build_links(uuid, host, endpoints, brand))

    if fmt == "raw":
        return body, plain, "autovless.txt"
    return _b64(body), plain, "autovless.txt"


def headers(fmt: str = "sub") -> dict[str, str]:
    """Subscription headers the client apps read."""
    return {
        "profile-update-interval": "6",
        "profile-title": settings.brand,
        "profile-web-page-url": origin(),
        "cache-control": "no-store",
        "access-control-allow-origin": "*",
    }


__all__ = [
    "FORMATS",
    "enabled",
    "headers",
    "link",
    "links",
    "origin",
    "parse",
    "render",
    "resolve",
    "token",
]
