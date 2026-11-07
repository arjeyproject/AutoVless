"""Proxy Chain: several proxies walked in order, on purpose.

A chain here is an ordered list of proxy links. The generated Xray config
wires them with ``proxySettings`` - the core's own chaining primitive - so the
traffic of hop N travels *inside* the tunnel of hop N-1 and the address the
world sees belongs to the last hop. This is not "more configs in one file":
the wiring is explicit, validated, and testable before it is exported.

Validation is structural first (every hop parses, no hop appears twice, two
hops never repeat the same server, the count stays inside what is useful) and
then real: the enabled chain runs through the xray core and only a measured
answer from the far end counts as working.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from . import xraycore
from .pingtest import LinkError, TestResult, parse_link

log = logging.getLogger("autovless.chain")

MAX_HOPS = 4


def normalise_hops(raw: object) -> list[str]:
    """The stored hops JSON as a list of link strings, deduplicated in order."""
    try:
        parsed = json.loads(str(raw or "[]"))
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        link = str(item or "").strip()
        if link and link not in out:
            out.append(link)
    return out


def validate(hops: list[str]) -> tuple[bool, str, list[dict]]:
    """Structural validation. Returns ``(ok, reason_key, parsed_hops)``.

    Reason keys are i18n keys - the screens translate them, this module never
    invents user-facing text.
    """
    if not hops:
        return False, "chain_empty", []
    if len(hops) > MAX_HOPS:
        return False, "chain_too_long", []

    parsed: list[dict] = []
    seen_servers: set[tuple[str, int]] = set()
    for index, link in enumerate(hops, start=1):
        try:
            item = parse_link(link)
        except LinkError as error:
            return False, "chain_hop_bad", []
        if str(item.get("transport")) in ("grpc", "reality", "quic") and not xraycore.available():
            return False, "chain_hop_core", []
        server = (str(item["host"]).lower(), int(item["port"]))
        if server in seen_servers:
            return False, "chain_loop", []
        seen_servers.add(server)
        parsed.append(item)
    return True, "", parsed


def describe(hops: list[str], lang: str, parsed: Optional[list[dict]] = None) -> str:
    """The visual line for a chain: hop names joined by arrows."""
    try:
        items = parsed or [parse_link(link) for link in hops]
    except LinkError:
        items = []
    names = []
    for item in items:
        label = str(item.get("name") or "").strip()
        host = str(item.get("host") or "")
        names.append(f"{label} ({host})" if label else host)
    arrow = " ← " if lang != "en" else " -> "
    return arrow.join(names) if names else "-"


def build_config(parsed_hops: list[dict], *, listen_port: int = 10808) -> dict:
    """The runnable Xray config for this chain."""
    outbounds = [xraycore.outbound_from_params(item, f"hop{index}") for index, item in enumerate(parsed_hops, start=1)]
    return xraycore.chain_config(outbounds, listen_port=listen_port)


async def test(parsed_hops: list[dict], *, timeout: float = 20.0) -> TestResult:
    """Measure the chain end to end through the core.

    The exit address that comes back belongs to the LAST hop - which is the
    whole point of the feature, and the one number a user cannot fake.
    """
    if not xraycore.available():
        return TestResult(ok=False, error_kind="unsupported", error_detail="needs the xray core", method="chain")
    try:
        config = build_config(parsed_hops)
        latency, exit_ip, exit_country = await asyncio_wait(config, timeout)
        return TestResult(
            ok=True,
            latency_ms=round(latency, 1),
            exit_ip=exit_ip,
            exit_country=exit_country,
            method="chain",
            rounds=len(parsed_hops),
        )
    except Exception as error:  # noqa: BLE001
        from .pingtest import classify_error

        kind, detail = classify_error(error)
        text = str(error)
        if "status 403" in text or "status 40" in text:
            kind = "handshake"
            detail = "edge refused the chain with 403 (waf/bot protection)"
        return TestResult(ok=False, error_kind=kind, error_detail=detail[:200], method="chain")


async def asyncio_wait(config: dict, timeout: float) -> tuple[float, str, str]:
    return await xraycore.run_config(config, timeout=timeout)
