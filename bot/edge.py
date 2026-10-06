"""Custom-domain front door for every panel.

Why this exists
---------------
Every config the bot used to hand out carried ``<script>.<sub>.workers.dev`` as
its TLS SNI and its WebSocket ``Host``. The address field held a clean
Cloudflare IP, so DNS poisoning never mattered for the tunnel - but the SNI
does. Iranian DPI reads the ClientHello, sees ``workers.dev`` and drops the
handshake. On port 80 the same name crosses the wire in a plain ``Host`` header
and dies the same way. That is the whole story behind "every config shows -1":
the server-side acceptance check runs from a VPS abroad, where workers.dev is
fine, so it passed every endpoint while not a single one could ping in Iran.

The fix is to stop using workers.dev as the front door. If the user's
Cloudflare account holds any active zone (a free domain is enough), the panel
worker is attached to ``<label>.<zone>`` through Workers Custom Domains and that
hostname becomes SNI and Host in every config. Cloudflare routes on SNI, so the
clean IP in the address field still works as the entry point.

Settings (environment)
----------------------
``CUSTOM_DOMAIN``  ``true`` (default) / ``false``
``CUSTOM_ZONE``    pin one zone name; blank picks the shortest active zone
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from .cloudflare import CloudflareClient, CloudflareError

log = logging.getLogger("autovless.edge")

DEV_SUFFIX = ".workers.dev"

# The token button, with Workers Routes: Edit added. Custom Domains need it on
# the zone side; the rest is unchanged from keyboards.CF_TOKEN_URL.
TOKEN_URL = (
    "https://dash.cloudflare.com/profile/api-tokens"
    "?permissionGroupKeys=%5B%7B%22key%22%3A%22workers_scripts%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C"
    "%7B%22key%22%3A%22workers_routes%22%2C%22type%22%3A%22edit%22%7D%2C"
    "%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D"
    "&accountId=*&zoneId=all&name=AutoVless"
)


def _install_token_url() -> None:
    """Point the token button at the URL with the extra permission."""
    try:
        from . import keyboards

        keyboards.CF_TOKEN_URL = TOKEN_URL
    except Exception:  # noqa: BLE001
        log.debug("could not patch the token url", exc_info=True)


_install_token_url()


def enabled() -> bool:
    raw = (os.getenv("CUSTOM_DOMAIN") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def pinned_zone() -> str:
    return (os.getenv("CUSTOM_ZONE") or "").strip().lower().rstrip(".")


def is_dev_host(host: object) -> bool:
    return str(host or "").strip().lower().endswith(DEV_SUFFIX)


def label_for(script: str) -> str:
    """A stable, ordinary-looking first-level label for this script.

    Stable so a rebuild or refresh re-attaches the same hostname instead of
    piling up new ones. First-level so the zone's Universal SSL certificate
    already covers it and nothing waits on certificate issuance.
    """
    digest = hashlib.sha256(f"avl:{script}".encode("utf-8")).hexdigest()
    head = chr(ord("a") + int(digest[0], 16) % 26)
    return f"{head}{digest[1:10]}"


async def pick_zone(cf: CloudflareClient, account_id: str) -> Optional[dict]:
    zones = await cf.list_zones(account_id)
    active = [
        zone
        for zone in zones
        if str(zone.get("status") or "").lower() == "active" and zone.get("name") and zone.get("id")
    ]
    want = pinned_zone()
    if want:
        return next((zone for zone in active if str(zone["name"]).lower() == want), None)
    active.sort(key=lambda zone: (len(str(zone["name"])), str(zone["name"])))
    return active[0] if active else None


async def attach(cf: CloudflareClient, account_id: str, script: str) -> str:
    """Route ``<label>.<zone>`` to ``script``. Returns the hostname or ``""``."""
    if not enabled():
        return ""
    try:
        zone = await pick_zone(cf, account_id)
    except CloudflareError as error:
        log.info("zone lookup failed for %s: %s", account_id, error.message)
        return ""
    if not zone:
        log.info("account %s has no active zone; panel stays on workers.dev", account_id)
        return ""

    hostname = f"{label_for(script)}.{str(zone['name']).lower()}"
    try:
        await cf.attach_domain(account_id, str(zone["id"]), str(zone["name"]), hostname, script)
    except CloudflareError as error:
        log.warning("could not attach %s to %s: %s", hostname, script, error.message)
        return ""
    log.info("attached custom domain %s -> %s", hostname, script)
    return hostname


__all__ = [
    "DEV_SUFFIX",
    "TOKEN_URL",
    "attach",
    "enabled",
    "is_dev_host",
    "label_for",
    "pick_zone",
    "pinned_zone",
]
