#!/usr/bin/env python3
"""Runtime checks for a deployed AutoVless panel.

This is intentionally read-only. It checks the public Worker health endpoint and
its outbound probe, then checks each stored endpoint through the same TLS/SNI and
WebSocket path used by the bot probe module when run inside the application
container. It never labels TCP connect alone as a healthy proxy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from urllib.parse import urlparse

import httpx

from bot import probe
from bot.vless import WS_PATH, is_tls


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an AutoVless panel")
    parser.add_argument("panel", help="panel URL, for example https://host/uuid")
    parser.add_argument("--endpoint", action="append", default=[], help="IP:port to verify; repeatable")
    args = parser.parse_args()

    base = args.panel.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        parser.error("panel must be an http(s) URL")

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        checks = {}
        for name in ("health", "probe"):
            try:
                response = await client.get(f"{base}/{name}")
                checks[name] = {
                    "status": response.status_code,
                    "ok": response.status_code == 200 and bool(response.json().get("ok")),
                }
            except Exception as exc:  # pragma: no cover - CLI failure path
                checks[name] = {"ok": False, "error": str(exc)}

    rows = []
    for raw in args.endpoint:
        host, sep, port_text = raw.rpartition(":")
        if not sep or not host or not port_text.isdigit():
            rows.append({"endpoint": raw, "healthy": False, "error": "expected IP:port"})
            continue
        port = int(port_text)
        result = await probe.measure(
            host,
            port,
            tls=is_tls(port),
            host=parsed.hostname,
            path=WS_PATH,
            rounds=3,
            required=2,
            timeout=8,
        )
        rows.append({"endpoint": raw, "healthy": result is not None, "probe": result})

    report = {"panel": base, "worker": checks, "endpoints": rows}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all(item.get("ok", False) for item in checks.values()) and all(item["healthy"] for item in rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
