"""Config assembly: endpoints, VLESS links, Clash and sing-box exports."""

from __future__ import annotations

import base64
import json
import logging
import uuid as uuid_lib
from typing import Iterable, Optional
from urllib.parse import quote, urlencode

from .config import settings

log = logging.getLogger("autovless.vless")

WS_PATH = "/?ed=2560"


def new_uuid() -> str:
    return str(uuid_lib.uuid4())


def is_tls(port: int) -> bool:
    return int(port) in settings.tls_ports


def group_of(port: int) -> str:
    return "tls" if is_tls(port) else "http"


def _normalise(row: dict, kind: str = "") -> dict:
    return {
        "ip": str(row["ip"]),
        "port": int(row["port"]),
        "latency": round(float(row.get("latency") or 0), 1),
        "jitter": round(float(row.get("jitter") or 0), 1),
        "colo": row.get("colo") or "CF",
        "kind": kind or str(row.get("kind") or "ip"),
        "verified": bool(row.get("verified", True)),
    }


def _rank(row: dict) -> float:
    return float(row["latency"]) + float(row["jitter"]) * 2


async def _buckets(scanner, ports: Iterable[int], depth: int) -> dict[int, list[dict]]:
    """Verified rows per port, best first.

    Unverified rows are dropped here and nowhere else, so no later step has to
    remember not to ship them.
    """
    out: dict[int, list[dict]] = {}
    for port in ports:
        rows = [_normalise(row) for row in await scanner.pick(int(port), depth)]
        rows = [row for row in rows if row["verified"] and int(row["port"]) == int(port)]
        rows.sort(key=_rank)
        if rows:
            out[int(port)] = rows
    return out


def _spread(buckets: dict[int, list[dict]], needed: int, used: set[str]) -> list[dict]:
    """Fill a group by walking its ports in turn.

    Taking the globally fastest rows would put every config in a group on one
    port, because whichever port the nearest colo answers quickest wins every
    comparison. Then the day that port is filtered on someone's ISP, the whole
    group dies at once. Round-robin costs a few milliseconds and buys the user a
    second and third way in.
    """
    chosen: list[dict] = []
    if needed <= 0 or not buckets:
        return chosen

    cursors = {port: 0 for port in buckets}

    # One self-healing hostname up front whenever the group can spare a slot:
    # the address behind it is replaced upstream, so that entry keeps working
    # long after every raw address in the list has gone stale.
    if needed >= 2:
        for port in buckets:
            hostname = next(
                (row for row in buckets[port] if row["kind"] == "domain" and row["ip"] not in used),
                None,
            )
            if hostname is not None:
                used.add(hostname["ip"])
                chosen.append(hostname)
                break

    while len(chosen) < needed:
        progressed = False
        for port in list(buckets):
            if len(chosen) >= needed:
                break
            rows = buckets[port]
            index = cursors[port]
            while index < len(rows):
                row = rows[index]
                index += 1
                if row["ip"] in used:
                    continue
                used.add(row["ip"])
                chosen.append(row)
                progressed = True
                break
            cursors[port] = index
        if not progressed:
            break

    return chosen


async def collect_endpoints(
    scanner,
    tls_count: Optional[int] = None,
    http_count: Optional[int] = None,
) -> list[dict]:
    """Pick the entry points a panel ships with.

    Three rules, and the first one is the reason this function was rewritten:

      * an endpoint that has not been verified is never handed to a user. The
        old last-resort branch pulled rows with ``verified_only=False`` so that
        the count always came out right, which is how a thin TLS pool turned
        into five configs that could not ping. Fewer working configs beat a full
        set of dead ones every single time.
      * every group is spread across all of its ports, so no single filtered
        port can empty a group.
      * slots a group cannot fill honestly move to a group that can.
    """
    tls_needed = settings.tls_config_count if tls_count is None else max(0, int(tls_count))
    http_needed = settings.http_config_count if http_count is None else max(0, int(http_count))

    plans = [
        {"key": "tls", "ports": tuple(settings.tls_ports), "needed": tls_needed, "chosen": []},
        {"key": "http", "ports": tuple(settings.http_ports), "needed": http_needed, "chosen": []},
    ]

    used: set[str] = set()
    pools: dict[str, dict[int, list[dict]]] = {}

    for plan in plans:
        if plan["needed"] <= 0 or not plan["ports"]:
            pools[plan["key"]] = {}
            continue
        depth = max(12, plan["needed"] * 6)
        pools[plan["key"]] = await _buckets(scanner, plan["ports"], depth)
        plan["chosen"] = _spread(pools[plan["key"]], plan["needed"], used)

    shortfall = sum(max(0, plan["needed"] - len(plan["chosen"])) for plan in plans)
    if shortfall:
        log.warning(
            "short by %s verified endpoint(s): %s",
            shortfall,
            ", ".join(f"{plan['key']}={len(plan['chosen'])}/{plan['needed']}" for plan in plans),
        )
        for plan in plans:
            if shortfall <= 0:
                break
            extra = _spread(pools.get(plan["key"]) or {}, shortfall, used)
            plan["chosen"].extend(extra)
            shortfall -= len(extra)

    endpoints = [row for plan in plans for row in plan["chosen"]]
    log.info(
        "selected %s endpoints (%s)",
        len(endpoints),
        ", ".join(f"{row['ip']}:{row['port']}" for row in endpoints) or "none",
    )
    return endpoints


async def spare_endpoints(
    scanner,
    ports: Iterable[int],
    count: int,
    exclude: Iterable[str] = (),
) -> list[dict]:
    """Replacements for endpoints that failed their acceptance check."""
    if count <= 0:
        return []
    used = {str(item) for item in exclude}
    buckets = await _buckets(scanner, ports, max(16, count * 8))
    return _spread(buckets, count, used)


def remark(endpoint: dict, index: int, brand: str = "") -> str:
    brand = brand or settings.brand
    secure = is_tls(endpoint["port"])
    if endpoint.get("kind") == "domain":
        badge = "\U0001f300"
    else:
        badge = "\u26a1" if secure else "\U0001f7e1"
    ping = f"{round(float(endpoint.get('latency') or 0))}ms" if endpoint.get("latency") else "auto"
    tail = "" if secure else f" | \U0001f50c{endpoint['port']}"
    port_tag = f" | \U0001f512{endpoint['port']}" if secure and int(endpoint["port"]) != 443 else ""
    return (
        f"@{brand} | {badge} VLESS | \U0001f30d GLOBAL | {ping} | "
        f"{endpoint.get('colo') or 'CF'}{port_tag}{tail} | #{index}"
    )


def build_link(uuid: str, host: str, endpoint: dict, index: int, brand: str = "") -> str:
    secure = is_tls(endpoint["port"])
    params = {
        "encryption": "none",
        "security": "tls" if secure else "none",
        "type": "ws",
        "host": host,
        "path": WS_PATH,
    }
    if secure:
        params.update({"sni": host, "fp": "chrome", "alpn": "http/1.1"})
    query = urlencode(params, quote_via=quote, safe="")
    label = quote(remark(endpoint, index, brand), safe="")
    return f"vless://{uuid}@{endpoint['ip']}:{endpoint['port']}?{query}#{label}"


def build_links(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> list[str]:
    return [build_link(uuid, host, ep, i + 1, brand) for i, ep in enumerate(endpoints)]


def build_subscription(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    payload = "\n".join(build_links(uuid, host, endpoints, brand))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def sub_url(uuid: str, host: str, fmt: str = "") -> str:
    suffix = f"/{fmt}" if fmt else ""
    return f"https://{host}/{uuid}{suffix}"


def build_clash(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    brand = brand or settings.brand
    proxies: list[str] = []
    names: list[str] = []

    for index, endpoint in enumerate(endpoints, start=1):
        secure = is_tls(endpoint["port"])
        name = remark(endpoint, index, brand).replace('"', "'")
        names.append(f'      - "{name}"')
        lines = [
            f'  - name: "{name}"',
            "    type: vless",
            f"    server: {endpoint['ip']}",
            f"    port: {endpoint['port']}",
            f"    uuid: {uuid}",
            "    udp: true",
            f"    tls: {'true' if secure else 'false'}",
        ]
        if secure:
            lines += [f"    servername: {host}", "    client-fingerprint: chrome"]
        lines += [
            "    network: ws",
            "    ws-opts:",
            f'      path: "{WS_PATH}"',
            "      headers:",
            f"        Host: {host}",
        ]
        proxies.append("\n".join(lines))

    return "\n".join(
        [
            f"# {brand} - built on your own Cloudflare account",
            "mixed-port: 7890",
            "allow-lan: false",
            "mode: rule",
            "log-level: warning",
            "proxies:",
            "\n".join(proxies),
            "proxy-groups:",
            f'  - name: "{brand}"',
            "    type: url-test",
            "    url: http://cp.cloudflare.com/generate_204",
            "    interval: 300",
            "    tolerance: 50",
            "    proxies:",
            "\n".join(names),
            "rules:",
            f"  - MATCH,{brand}",
            "",
        ]
    )


def build_singbox(uuid: str, host: str, endpoints: list[dict], brand: str = "") -> str:
    outbounds = []
    for index, endpoint in enumerate(endpoints, start=1):
        secure = is_tls(endpoint["port"])
        item: dict = {
            "type": "vless",
            "tag": remark(endpoint, index, brand),
            "server": endpoint["ip"],
            "server_port": int(endpoint["port"]),
            "uuid": uuid,
            "packet_encoding": "xudp",
            "transport": {
                "type": "ws",
                "path": WS_PATH,
                "headers": {"Host": host},
                "early_data_header_name": "Sec-WebSocket-Protocol",
            },
        }
        if secure:
            item["tls"] = {
                "enabled": True,
                "server_name": host,
                "utls": {"enabled": True, "fingerprint": "chrome"},
            }
        outbounds.append(item)
    return json.dumps({"outbounds": outbounds}, indent=2, ensure_ascii=False)


def parse_vless(link: str) -> dict:
    """Parse a vless:// link into the endpoint dict shape used above."""
    from urllib.parse import parse_qs, unquote, urlparse

    if not link.strip().lower().startswith("vless://"):
        raise ValueError("not a vless link")

    parsed = urlparse(link.strip())
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ValueError("incomplete vless link")

    return {
        "uuid": parsed.username,
        "ip": parsed.hostname,
        "port": int(parsed.port),
        "host": query.get("host") or query.get("sni") or parsed.hostname,
        "path": unquote(query.get("path") or WS_PATH),
        "security": query.get("security") or "none",
        "name": unquote(parsed.fragment or "config"),
        "latency": 0,
        "jitter": 0,
        "kind": "ip",
        "colo": "CF",
    }
