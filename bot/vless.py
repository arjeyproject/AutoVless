"""Config assembly: endpoints, VLESS links, Clash and sing-box exports."""

from __future__ import annotations

import base64
import json
import uuid as uuid_lib
from urllib.parse import quote, urlencode

from .config import settings

WS_PATH = "/?ed=2560"


def new_uuid() -> str:
    return str(uuid_lib.uuid4())


def is_tls(port: int) -> bool:
    return int(port) in settings.tls_ports


async def collect_endpoints(scanner) -> list[dict]:
    """Pick the fastest verified endpoints: TLS ports first, then plain HTTP ports."""
    endpoints: list[dict] = []
    seen: set[str] = set()

    plans = (
        (settings.tls_ports, settings.tls_config_count),
        (settings.http_ports, settings.http_config_count),
    )
    for ports, needed in plans:
        if needed <= 0 or not ports:
            continue
        bucket: list[dict] = []
        for port in ports:
            bucket.extend(await scanner.pick(port, needed * 2))
        bucket.sort(key=lambda row: row["latency"])
        for row in bucket:
            if row["ip"] in seen:
                continue
            seen.add(row["ip"])
            endpoints.append(
                {
                    "ip": row["ip"],
                    "port": int(row["port"]),
                    "latency": round(float(row["latency"]), 1),
                    "colo": row.get("colo") or "CF",
                }
            )
            if len([e for e in endpoints if int(e["port"]) in ports]) >= needed:
                break

    return endpoints


def remark(endpoint: dict, index: int, brand: str = "") -> str:
    brand = brand or settings.brand
    secure = is_tls(endpoint["port"])
    badge = "\u26a1" if secure else "\U0001f7e1"
    ping = f"{round(float(endpoint.get('latency') or 0))}ms" if endpoint.get("latency") else "-"
    tail = "" if secure else f" | \U0001f50c{endpoint['port']}"
    return f"@{brand} | {badge} VLESS | \U0001f30d GLOBAL | {ping} | {endpoint.get('colo') or 'CF'}{tail} | #{index}"


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
        "colo": "CF",
    }
