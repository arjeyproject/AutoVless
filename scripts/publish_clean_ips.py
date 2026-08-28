#!/usr/bin/env python3
"""Run the clean-IP sweep and publish the survivors as a seed list.

This is the scheduled half of clean-IP discovery. The bot's own sweep keeps
running on the VPS, because entry-point health is relative to the network you
measure from, but a scan that only ever happens on one box has one blind spot and
no history. This runs on a schedule from a different network entirely and commits
what it found, so:

  * a fresh deployment starts warm instead of blind
  * the bot reads endpoints/clean-ips.txt as a local seed (CLEAN_IP_FILES), which
    works exactly the same whether the repository is public or private
  * the list is a diffable record of what was actually reachable, and when

Set the VERIFY_HOST environment variable to a live panel hostname and the sweep
verifies TLS ports with the same real WebSocket upgrade the bot demands before it
ships a config. Without it the weaker cold-start trace check is used, which is
fine for seeding but proves less.

Usage:
    python scripts/publish_clean_ips.py --out endpoints/clean-ips [--allow-empty]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import db  # noqa: E402
from bot.config import settings  # noqa: E402
from bot.scanner import scanner  # noqa: E402

log = logging.getLogger("autovless.publish")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="scan Cloudflare edges and publish a seed list")
    parser.add_argument("--out", default="endpoints/clean-ips", help="output path without extension")
    parser.add_argument("--per-port", type=int, default=25, help="addresses kept per port")
    parser.add_argument("--batch", type=int, default=0, help="override SCAN_BATCH for this run")
    parser.add_argument("--allow-empty", action="store_true", help="exit 0 when nothing verified")
    return parser.parse_args()


async def collect(per_port: int, batch: int) -> dict:
    await db.init()
    try:
        found = await scanner.scan_once(batch=batch or None)
        ports: dict[str, list[dict]] = {}
        for port in settings.all_ports:
            rows = await db.best_ips(int(port), per_port)
            keep = [row for row in rows if str(row.get("kind") or "ip") == "ip"]
            if keep:
                ports[str(int(port))] = keep
        return {"found": found, "ports": ports}
    finally:
        await db.close()


def render(payload: dict) -> tuple[str, str]:
    ports = payload["ports"]
    total = sum(len(rows) for rows in ports.values())
    document = {
        "generated_at": int(time.time()),
        "count": total,
        "verified_this_run": payload["found"],
        "ports": {
            port: [
                {
                    "ip": str(row["ip"]),
                    "port": int(row["port"]),
                    "latency": round(float(row.get("latency") or 0), 1),
                    "jitter": round(float(row.get("jitter") or 0), 1),
                    "colo": row.get("colo") or "CF",
                }
                for row in rows
            ]
            for port, rows in sorted(ports.items(), key=lambda item: int(item[0]))
        },
    }

    lines = [
        "# AutoVless clean IP seed list",
        "# ip:port # COLO latency",
        f"# generated {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())} "
        f"({total} addresses)",
    ]
    for port, rows in document["ports"].items():
        lines.append(f"# --- port {port} ---")
        for row in rows:
            lines.append(
                f"{row['ip']}:{row['port']} # {row['colo']} {round(row['latency'])}ms"
            )
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n", "\n".join(lines) + "\n"


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s")
    args = _args()
    payload = await collect(max(4, args.per_port), max(0, args.batch))
    total = sum(len(rows) for rows in payload["ports"].values())

    if not total:
        # An empty run is a real answer, not a reason to wipe a good list.
        log.warning("no address verified, leaving the existing list untouched")
        return 0 if args.allow_empty else 1

    document, text = render(payload)
    base = Path(args.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(document, encoding="utf-8")
    base.with_suffix(".txt").write_text(text, encoding="utf-8")
    log.info("published %s addresses across %s ports", total, len(payload["ports"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
