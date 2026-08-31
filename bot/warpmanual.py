"""Endpoints an admin typed in by hand: parse them, prove them, pin them.

Why this exists
---------------
Scanning is the right way to fill a pool and it is not always a *possible* way.
Cloudflare's IPv6 WARP prefixes are reachable from an Irancell handset and not
from most Iranian VPS hosts, so the box doing the scanning frequently has no
IPv6 route at all and the IPv6 pool - the one Irancell users need - can never
fill no matter how many times anybody presses refresh. Meanwhile the admin is
holding a list of IPv6 endpoints that demonstrably work on the phone in their
hand. This module is the door for that list.

Rules, in order of stubbornness
-------------------------------
1. **A pool only ever holds healthy endpoints.** A pasted address gets exactly
   the same treatment a scanned one gets: several spaced, cryptographically
   verified WireGuard handshakes, then WarpEP's health floor. Anything that does
   not answer, or answers badly, is reported back line by line and never written.
2. **When this host cannot test a family, say so rather than lie.** With no route
   there is no handshake to be had, and the choice is between storing the address
   untested or refusing the one feature that exists for this exact situation. It
   is stored, marked untested (``latency = 0``, ``verified = -1``) and it sorts
   *behind* every measured endpoint, so a proven address always goes out first.
   The report says which of the two happened, every time.
3. **Manual rows are pinned.** ``warpstore`` never trims, retires or purges an
   endpoint an admin typed in, and one that dies is sidelined rather than
   deleted, so it stays visible on the screen that owns it and the agent can
   bring it back by itself when it starts working again.

Parsing is deliberately forgiving, because the real input is a paste from a
channel: newlines, spaces, commas, Persian commas, bullets, Persian digits and
``[v6]:port`` brackets all work, and a bare address means port 2408.

Nothing here blocks the bot. Parsing is instant; the probing runs as a
background task and edits the message that started it.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from . import db, warpep, warpstore
from .warpep import V4, V6
from .warpscan import warp_scanner
from .warptune import TUNE

log = logging.getLogger("autovless.warpmanual")

# What a bare address means. 2408 is WARP's own default and the port that
# survives on the most networks.
DEFAULT_PORT = 2408

# Separators worth honouring in a paste: whitespace, commas, semicolons, pipes
# and the Persian comma.
_SPLIT = re.compile("[\\s,;|\u060c]+")

# Invisible direction marks and stray quoting survive every copy and paste and
# turn a perfectly good address into an unparseable one.
_JUNK = str.maketrans(
    {
        "\u200b": None,
        "\u200c": None,
        "\u200d": None,
        "\u200e": None,
        "\u200f": None,
        "\u202a": None,
        "\u202b": None,
        "\u202c": None,
        "\ufeff": None,
        '"': None,
        "'": None,
        "`": None,
        "<": None,
        ">": None,
    }
)

# An admin typing on a Persian keyboard produces Persian digits, and
# ``int("\u06f2\u06f4\u06f0\u06f8")`` is not a port anybody wants to debug.
_DIGITS = str.maketrans(
    {
        **{chr(0x06F0 + index): str(index) for index in range(10)},
        **{chr(0x0660 + index): str(index) for index in range(10)},
    }
)

VERDICTS = ("stored", "untested", "dead", "weak", "family", "dup", "bad", "over")


@dataclass
class Entry:
    """One line of the paste, and what became of it."""

    raw: str
    ip: str = ""
    port: int = 0
    family: str = ""
    verdict: str = "bad"
    latency: Optional[float] = None
    loss: float = 0.0
    health: int = 0

    @property
    def label(self) -> str:
        if self.ip:
            return warpep.host_port(self.ip, self.port)
        return self.raw[:48]


@dataclass
class ImportReport:
    """What one paste did to a pool, in a shape the handler renders directly."""

    family: str = V4
    # done | empty | none | identity | disabled
    status: str = "done"
    # False means "this host has no route for the family, so nothing could be
    # measured here". It changes what every number below is worth, so it is not
    # hidden in a log line.
    tested: bool = True
    entries: list[Entry] = field(default_factory=list)
    stored: int = 0
    untested: int = 0
    dead: int = 0
    weak: int = 0
    skipped: int = 0
    pool: int = 0
    manual: int = 0
    manual_healthy: int = 0
    elapsed: float = 0.0
    reason: str = ""

    @property
    def accepted(self) -> int:
        return self.stored + self.untested


# --------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------- #


def _clean(token: str) -> str:
    return token.translate(_JUNK).translate(_DIGITS).strip().strip("-\u2022\u00b7*\u2192").strip()


def _pair(host: str, port: int) -> Optional[tuple[str, int]]:
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError:
        return None
    if not 0 < int(port) < 65536:
        return None
    return str(address), int(port)


def parse_one(token: str) -> Optional[tuple[str, int]]:
    """``ip``, ``ip:port``, ``[v6]`` or ``[v6]:port`` into one endpoint.

    A bare IPv6 literal is tried as an address *before* the last colon is read as
    a port, because ``2606:4700:d0::a29f:c001`` is a perfectly good address whose
    last group looks exactly like one. That is also why the bracket form is the
    documented way to give an IPv6 port: nothing can tell
    ``2606:4700:d0::a29f:c001:2408`` apart from an address, and guessing wrong
    hands a user a config that cannot connect.
    """
    text = _clean(token)
    if not text:
        return None

    if text.startswith("["):
        host, closed, tail = text[1:].partition("]")
        if not closed:
            return None
        if not tail:
            return _pair(host, DEFAULT_PORT)
        if tail.startswith(":") and tail[1:].isdigit():
            return _pair(host, int(tail[1:]))
        return None

    try:
        ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        return _pair(text, DEFAULT_PORT)

    host, colon, tail = text.rpartition(":")
    if colon and tail.isdigit():
        return _pair(host, int(tail))
    return None


def tokens_of(text: str) -> list[str]:
    """Every candidate in a paste, in the order it was written."""
    found: list[str] = []
    for line in (text or "").splitlines():
        for token in _SPLIT.split(line):
            cleaned = _clean(token)
            if cleaned:
                found.append(cleaned)
    return found


# --------------------------------------------------------------------- #
# the import
# --------------------------------------------------------------------- #


async def import_pool(family: str, text: str) -> ImportReport:
    """Parse, prove and pin a pasted list into one family's pool. Never raises."""
    started = time.perf_counter()
    code = warpep.normalise_family(family)
    report = ImportReport(family=code)

    tokens = tokens_of(text)
    if not tokens:
        report.status = "empty"
        return report

    cap = max(1, int(TUNE.manual_max))
    seen: set[tuple[str, int]] = set()
    entries: list[Entry] = []
    accepted: list[Entry] = []

    for token in tokens:
        entry = Entry(raw=token)
        entries.append(entry)
        if len(accepted) >= cap:
            entry.verdict = "over"
            continue
        parsed = parse_one(token)
        if parsed is None:
            entry.verdict = "bad"
            continue
        entry.ip, entry.port = parsed
        entry.family = warpep.family_of(entry.ip)
        if entry.family != code:
            # Deliberately not "helpfully" filed into the other pool. The admin
            # pressed a button that says IPv4 or IPv6, and quietly doing the
            # other thing is how an Irancell user ends up on an IPv4 endpoint.
            entry.verdict = "family"
            continue
        if (entry.ip, entry.port) in seen:
            entry.verdict = "dup"
            continue
        seen.add((entry.ip, entry.port))
        accepted.append(entry)

    report.entries = entries
    if not accepted:
        report.status = "none"
        report.skipped = len(entries)
        return report

    report.tested = warpep.reachable(code)
    floor = int(TUNE.health_floor)

    if report.tested:
        identity = await warp_scanner.identity()
        if identity is None:
            report.status = "identity"
            report.reason = "warp identity unavailable"
            return report

        semaphore = asyncio.Semaphore(4)

        async def check(entry: Entry) -> Optional[dict]:
            async with semaphore:
                return await warp_scanner.measure(
                    entry.ip,
                    entry.port,
                    probes=int(TUNE.manual_probes),
                    identity=identity,
                )

        results = await asyncio.gather(
            *(check(entry) for entry in accepted), return_exceptions=True
        )
        keepers: list[dict] = []
        for entry, item in zip(accepted, results):
            if isinstance(item, BaseException) or item is None:
                entry.verdict = "dead"
                continue
            entry.latency = float(item["latency"])
            entry.loss = float(item["loss"])
            entry.health = int(
                item.get("health")
                or warpep.health(item["latency"], item["jitter"], item["loss"])
            )
            if entry.health < floor or not item.get("stable"):
                # It answered, so it is not dead, but it is not fit for a pool
                # either. Two different verdicts because they need two different
                # reactions from the admin.
                entry.verdict = "weak"
                continue
            entry.verdict = "stored"
            keepers.append(item)
        if keepers:
            await warpstore.add_manual(keepers, tested=True)
    else:
        for entry in accepted:
            entry.verdict = "untested"
            entry.health = floor
        await warpstore.add_manual(
            [{"ip": entry.ip, "port": entry.port} for entry in accepted], tested=False
        )

    report.stored = sum(1 for entry in entries if entry.verdict == "stored")
    report.untested = sum(1 for entry in entries if entry.verdict == "untested")
    report.dead = sum(1 for entry in entries if entry.verdict == "dead")
    report.weak = sum(1 for entry in entries if entry.verdict == "weak")
    report.skipped = sum(
        1 for entry in entries if entry.verdict in {"family", "dup", "bad", "over"}
    )

    counts = await warpstore.counts(code)
    manual = await warpstore.manual_counts(code)
    report.pool = int(counts["healthy"])
    report.manual = int(manual["total"])
    report.manual_healthy = int(manual["healthy"])
    report.elapsed = round(time.perf_counter() - started, 1)

    await db.log_event(
        "warp_manual",
        detail=(
            f"family={code} given={len(tokens)} stored={report.stored} "
            f"untested={report.untested} dead={report.dead} weak={report.weak} "
            f"skipped={report.skipped} manual={report.manual_healthy}/{report.manual} "
            f"pool={report.pool} tested={'yes' if report.tested else 'no'}"
        ),
    )
    log.info(
        "manual %s import: %s stored, %s untested, %s dead, %s weak, pool now %s",
        code,
        report.stored,
        report.untested,
        report.dead,
        report.weak,
        report.pool,
    )
    return report


# --------------------------------------------------------------------- #
# reads and removals, for the screen that owns them
# --------------------------------------------------------------------- #


async def listing(family: Optional[str] = None, limit: int = 60) -> list[dict]:
    return await warpstore.manual_rows(family, limit=limit)


async def state(family: str) -> dict:
    return await warpstore.manual_counts(family)


async def both() -> dict[str, dict]:
    return {code: await warpstore.manual_counts(code) for code in (V4, V6)}


async def clear(family: Optional[str] = None) -> int:
    """Forget the hand entered endpoints of one family, or of both."""
    removed = await warpstore.clear_manual(family)
    await db.log_event("warp_manual_clear", detail=f"family={family or 'all'} removed={removed}")
    return removed


async def recheck(family: Optional[str] = None) -> dict:
    """Re-probe the hand entered endpoints only. Cheap, and answers one question.

    The full audit walks both pools and takes a while; this walks the handful an
    admin typed in, which is usually the thing they are actually staring at.
    """
    rows = await warpstore.manual_rows(family, limit=120)
    outcome = {"checked": 0, "alive": 0, "dead": 0, "skipped": 0}
    for row in rows:
        code = warpep.family_of(row["ip"])
        if not warpep.reachable(code):
            outcome["skipped"] += 1
            continue
        outcome["checked"] += 1
        measured = await warp_scanner.measure(
            row["ip"], row["port"], probes=max(2, int(TUNE.manual_probes) - 1)
        )
        if measured is None:
            outcome["dead"] += 1
            await warpstore.drop(row["ip"], row["port"])
            continue
        points = warpep.health(measured["latency"], measured["jitter"], measured["loss"])
        if points < int(TUNE.health_floor) or not measured.get("stable"):
            outcome["dead"] += 1
            await warpstore.drop(row["ip"], row["port"])
            continue
        outcome["alive"] += 1
        await warpstore.mark_ok(
            row["ip"], row["port"], measured["latency"], measured["jitter"], measured["loss"]
        )
    return outcome
