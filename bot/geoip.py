"""Where a relay actually exits.

A relay is only useful for AI traffic if the address the far side sees is in a
country that AI service allows, and if it stops moving. Neither of those can be
guessed from a latency measurement, so the exit address is geolocated once and
the answer is cached in the database next to the relay.

Three keyless providers, tried in order. Every one of them is free and rate
limited, so the batch endpoint goes first (one request for a hundred addresses)
and the per-address ones are only there to cover a provider outage.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Iterable, Optional

import httpx

log = logging.getLogger("autovless.geoip")

BATCH_URL = (
    "http://ip-api.com/batch?fields=status,message,country,countryCode,isp,org,proxy,hosting,query"
)
SINGLE_URLS = (
    "https://ipwho.is/{ip}",
    "https://ipapi.co/{ip}/json/",
)
BATCH_SIZE = 100
TIMEOUT = 12.0


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(str(value))
        return True
    except ValueError:
        return False


async def resolve(host: str) -> Optional[str]:
    """The IPv4 address behind a relay hostname, or None."""
    host = str(host or "").strip().strip("[]")
    if not host:
        return None
    if _is_ip(host):
        return host
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM),
            timeout=6.0,
        )
    except (OSError, asyncio.TimeoutError):
        return None
    for info in infos:
        address = info[4][0]
        if _is_ip(address):
            return address
    return None


def _row(payload: dict) -> dict:
    connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
    isp = (
        payload.get("isp")
        or payload.get("org")
        or connection.get("isp")
        or connection.get("org")
        or ""
    )
    return {
        "ip": str(payload.get("query") or payload.get("ip") or ""),
        "country": str(payload.get("countryCode") or payload.get("country_code") or "").upper()[:2],
        "name": str(payload.get("country") or payload.get("country_name") or "")[:40],
        "isp": str(isp)[:60],
        "hosting": bool(payload.get("hosting")),
        "proxy": bool(payload.get("proxy")),
    }


async def _batch(client: httpx.AsyncClient, ips: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for start in range(0, len(ips), BATCH_SIZE):
        chunk = ips[start : start + BATCH_SIZE]
        try:
            response = await client.post(BATCH_URL, json=chunk)
            if response.status_code >= 400:
                continue
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict) or item.get("status") != "success":
                continue
            row = _row(item)
            if row["ip"] and row["country"]:
                out[row["ip"]] = row
        await asyncio.sleep(1.4)  # the free tier allows 15 batches a minute
    return out


async def _single(client: httpx.AsyncClient, ip: str) -> Optional[dict]:
    for template in SINGLE_URLS:
        try:
            response = await client.get(template.format(ip=ip))
            if response.status_code >= 400:
                continue
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        row = _row(payload)
        if row["country"]:
            row["ip"] = ip
            return row
    return None


async def locate(hosts: Iterable[str]) -> dict[str, dict]:
    """host -> {ip, country, name, isp, hosting, proxy} for everything we could place."""
    wanted = [str(host).strip() for host in hosts if str(host or "").strip()]
    if not wanted:
        return {}

    addresses: dict[str, str] = {}
    for host in dict.fromkeys(wanted):
        ip = await resolve(host)
        if ip:
            addresses[host] = ip

    if not addresses:
        return {}

    found: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"user-agent": "AutoVless/2.0"}) as client:
        by_ip = await _batch(client, list(dict.fromkeys(addresses.values())))
        missing = [ip for ip in dict.fromkeys(addresses.values()) if ip not in by_ip]
        for ip in missing[:20]:
            row = await _single(client, ip)
            if row:
                by_ip[ip] = row

    for host, ip in addresses.items():
        row = by_ip.get(ip)
        if row:
            found[host] = {**row, "ip": ip}
    log.info("geolocated %s of %s relays", len(found), len(addresses))
    return found
