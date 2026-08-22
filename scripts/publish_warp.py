#!/usr/bin/env python3
"""Publish the WARP endpoint pool as a plain, machine readable list.

Two modes:

  --mode db     read what the running bot has already measured (default)
  --mode scan   measure from scratch in a throwaway database, for CI runners

Writes ``<out>.json`` and ``<out>.txt``, prints a one line summary, and exits 1
when the list would be empty unless ``--allow-empty`` is given. That exit code is
the point: a cron job needs to tell "nothing changed" apart from "nothing worked".

Examples
--------

    python scripts/publish_warp.py --mode db --out endpoints/warp-endpoints
    python scripts/publish_warp.py --mode scan --out endpoints/warp-seed --sample 6

Note that ``--out`` is a basename without an extension. A dot in it will be
treated as one by ``Path.with_suffix``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the WARP endpoint pool")
    parser.add_argument(
        "--mode",
        choices=("db", "scan"),
        default="db",
        help="read the bot database, or run a fresh scan in a temporary one",
    )
    parser.add_argument(
        "--out",
        default="endpoints/warp-endpoints",
        help="output basename, without extension",
    )
    parser.add_argument("--limit", type=int, default=0, help="how many endpoints to write")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="addresses probed per Cloudflare prefix, scan mode only",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="exit 0 even when no endpoint answered",
    )
    return parser.parse_args(argv)


async def collect(mode: str, limit: int, sample: int) -> tuple[list[dict], dict]:
    # Imported late: in scan mode the environment has to be redirected at a
    # temporary database before bot.config reads it.
    from bot import db, warpstore

    await db.init()
    try:
        await warpstore.ensure_schema()
        if mode == "scan":
            from bot.warpscan import warp_scanner

            report = await warp_scanner.scan(force=True, sample=sample or None)
            print(
                f"scan: status={report.status} stable={report.found} alive={report.alive} "
                f"ports={','.join(str(port) for port in report.ports)} "
                f"elapsed={report.elapsed:.1f}s",
                file=sys.stderr,
            )
        rows = await warpstore.snapshot(limit or None)
        stats = await warpstore.stats()
    finally:
        await db.close()
    return rows, stats


def build_payload(rows: list[dict], stats: dict, mode: str) -> dict:
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": mode,
        "count": len(rows),
        "best_latency_ms": stats.get("best"),
        "pool": {
            "stable": stats.get("stable", 0),
            "total": stats.get("total", 0),
            "avg_loss": stats.get("loss", 0),
        },
        "endpoints": [
            {
                "endpoint": f"{row['ip']}:{int(row['port'])}",
                "ip": str(row["ip"]),
                "port": int(row["port"]),
                "latency_ms": round(float(row.get("latency") or 0), 1),
                "jitter_ms": round(float(row.get("jitter") or 0), 1),
                "loss": round(float(row.get("loss") or 0), 3),
                "score": round(float(row.get("score") or 0), 1),
                "stable": bool(row.get("stable")),
            }
            for row in rows
        ],
    }


def write_files(out: Path, payload: dict) -> tuple[Path, Path]:
    out.parent.mkdir(parents=True, exist_ok=True)
    json_path = out.with_suffix(".json")
    text_path = out.with_suffix(".txt")

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        f"# {payload['generated_at']} · source={payload['source']} · "
        f"{payload['count']} endpoints"
    ]
    for item in payload["endpoints"]:
        lines.append(
            f"{item['endpoint']}  # {item['latency_ms']}ms "
            f"jitter {item['jitter_ms']}ms "
            f"loss {round(item['loss'] * 100)}% "
            f"score {item['score']}"
        )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, text_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.mode == "scan" and not os.getenv("DB_PATH"):
        # Never touch the live database from CI.
        temp = Path(tempfile.mkdtemp(prefix="warpscan-"))
        os.environ["DATA_DIR"] = os.environ.get("DATA_DIR") or str(temp)
        os.environ["DB_PATH"] = str(temp / "scan.db")

    rows, stats = asyncio.run(collect(args.mode, args.limit, args.sample))
    payload = build_payload(rows, stats, args.mode)
    json_path, text_path = write_files(Path(args.out), payload)

    print(
        f"wrote {json_path} and {text_path}: {payload['count']} endpoints, "
        f"best {payload['best_latency_ms'] or '-'}ms"
    )
    if not rows and not args.allow_empty:
        print("no endpoints to publish", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
