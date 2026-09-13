"""One steady exit address for AI traffic, in a country those services allow.

Why this module exists
----------------------
"Everything works except Gemini" had three separate causes, and all three are
fixed here.

1. **The login and the app left through different addresses.** Google checks the
   session's IP on ``accounts.google.com`` and again on ``gemini.google.com``.
   Only the second host was on the AI list, so the sign-in went out through a
   Cloudflare datacentre and the app through a relay. Google reads that as a
   stolen session and sends the user back to the login page, forever. Every host
   in the Google identity path is now on the list, in ``EXTRA_AI_DOMAINS``.

2. **The relay moved.** The worker pins by destination hostname, so a list of
   several relays hands ``accounts.google.com`` one exit and
   ``gemini.google.com`` another - the same mismatch by a different route. The
   AI pool is therefore exactly *one* relay. The worker still walks the ordinary
   chain and then direct if that relay dies, so a single pin costs no
   reliability, and with one entry every AI host provably shares one address.

3. **The relay was in the wrong country.** Gemini is not served to Iran at all,
   so a relay that happens to exit in Tehran produces a region error no matter
   how fast it is. Relays are geolocated and the pin is drawn from
   ``PREFERRED`` - United States first, then the other countries Gemini is
   available in.

The pin is also *stored*, per panel uuid. Deriving it from the live relay list
meant it silently changed every time the pool gained or lost a host, which is the
behaviour these sites read as account abuse. A stored pin only moves when the
relay behind it actually dies.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, Sequence

from . import proxies, store
from .config import settings

log = logging.getLogger("autovless.aipin")

# The Google identity path, plus the hosts the Gemini web app itself talks to.
# The worker already carries gemini/aistudio/generativelanguage in its own
# defaults; these are the ones that were missing, and the login loop lived in the
# first three.
EXTRA_AI_DOMAINS: tuple[str, ...] = (
    "accounts.google.com",
    "accounts.youtube.com",
    "myaccount.google.com",
    "apis.google.com",
    "clients6.google.com",
    "content-push.googleapis.com",
    "googleusercontent.com",
    "gstatic.com",
    "notebooklm.google",
    "labs.google",
    "deepmind.google",
    "aitestkitchen.withgoogle.com",
    "chat.openai.com",
    "auth0.openai.com",
    "auth.openai.com",
    "ab.chatgpt.com",
    "cdn.oaistatic.com",
    "console.anthropic.com",
    "api.anthropic.com",
)

# Where an AI exit is allowed to be. United States first because it is the one
# country every one of these services is fully available in; the rest are there so
# a pool with no American relay still produces a working pin instead of none.
PREFERRED: tuple[str, ...] = (
    "US",
    "CA",
    "GB",
    "DE",
    "NL",
    "FR",
    "SE",
    "FI",
    "JP",
    "SG",
    "AU",
    "IE",
    "PL",
    "ES",
    "IT",
)

# Countries an AI pin is never allowed to sit in: the services either refuse them
# outright or answer with a region error, which is worse than a slow relay.
BLOCKED: tuple[str, ...] = ("IR", "RU", "CN", "CU", "SY", "KP", "BY", "VE")

LOOKUP_DEPTH = 40


def ai_domains() -> tuple[str, ...]:
    """The AI host list handed to the worker: configured plus the ones above."""
    return tuple(dict.fromkeys((*settings.ai_domains, *EXTRA_AI_DOMAINS)))


def _split(relay: str) -> tuple[str, int]:
    text = str(relay or "").strip()
    if not text:
        return "", 443
    if text.startswith("["):
        end = text.find("]")
        host = text[: end + 1]
        rest = text[end + 1 :]
        port = rest[1:] if rest.startswith(":") else ""
        return host, int(port) if port.isdigit() else 443
    if text.count(":") == 1:
        host, _, port = text.partition(":")
        return host, int(port) if port.isdigit() else 443
    return text, 443


def _label(host: str, port: int) -> str:
    return host if int(port) == 443 else f"{host}:{int(port)}"


def _deterministic(rows: Sequence[dict], uuid: str) -> dict:
    """Same panel, same relay, every single build.

    Spreading users across the good relays matters - one address carrying every
    account is its own kind of suspicious - but the spread has to be stable, so
    it comes from the uuid rather than from anything that moves.
    """
    seed = f"{settings.secret_key}:ai:{uuid}".encode("utf-8")
    offset = hashlib.sha256(seed).digest()[0] % len(rows)
    return dict(rows[offset])


async def _candidates() -> list[dict]:
    """Verified relays that are allowed to carry AI traffic, best country first."""
    pool = await proxies.best(LOOKUP_DEPTH, verified_only=True)
    if not pool:
        pool = await proxies.best(LOOKUP_DEPTH, verified_only=False)
    if not pool:
        return []

    await proxies.ensure_countries([row["host"] for row in pool])

    placed = await proxies.best(LOOKUP_DEPTH, verified_only=True, countries=PREFERRED)
    if not placed:
        placed = await proxies.best(LOOKUP_DEPTH, verified_only=False, countries=PREFERRED)
    if placed:
        rank = {code: index for index, code in enumerate(PREFERRED)}
        placed.sort(key=lambda row: (rank.get(str(row.get("country") or "").upper(), 99), row["latency"]))
        return placed

    # Nothing placed anywhere useful. Anything is better than nothing, except a
    # country that is guaranteed to answer with a region error.
    return [
        row
        for row in pool
        if str(row.get("country") or "").upper() not in BLOCKED
    ]


async def choose(relays: list[str], uuid: str) -> tuple[list[str], str]:
    """The AI relay list for one panel, and the country it exits in.

    Returns exactly one relay whenever there is one to return, for the reason in
    the module docstring. ``AI_PROXY_IP`` in the environment still wins outright:
    an operator with a static address wants that address.
    """
    if settings.ai_proxy_ip:
        return list(settings.ai_proxy_ip), "ENV"

    stored = await store.ai_pin(uuid)
    if stored:
        host, port = _split(str(stored["relay"]))
        row = await proxies.alive(host, port) if host else None
        country = str((row or {}).get("country") or stored.get("country") or "").upper()
        if row is not None and country not in BLOCKED:
            return [_label(host, port)], country or "??"
        log.info("ai pin %s for panel %s is gone, repinning", stored["relay"], uuid[:8])

    rows = await _candidates()
    if not rows:
        # Last resort: the chain the panel already has. No pin is worse than an
        # unplaced one, because then every AI host picks its own exit again.
        if relays:
            host, port = _split(relays[0])
            return [_label(host, port)], "??"
        return [], ""

    chosen = _deterministic(rows[: max(1, min(8, len(rows)))], uuid)
    host = str(chosen["host"])
    port = int(chosen.get("port") or 443)
    country = str(chosen.get("country") or "").upper() or "??"
    label = _label(host, port)
    await store.set_ai_pin(uuid, label, country)
    log.info("panel %s pinned to %s (%s) for AI traffic", uuid[:8], label, country)
    return [label], country


async def repin(uuid: str) -> tuple[list[str], str]:
    """Forget the stored pin and pick again. What the admin's re-pin button does."""
    await store.clear_ai_pin(uuid)
    return await choose([], uuid)


async def report() -> dict:
    """What the admin AI screen shows."""
    relay_stats = await proxies.stats()
    pins = await store.ai_pin_stats()
    return {
        "relays": relay_stats,
        "pins": pins,
        "domains": len(ai_domains()),
        "preferred": PREFERRED[0],
        "env_pin": list(settings.ai_proxy_ip),
    }
