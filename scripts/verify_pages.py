"""Offline verification of the Pages pipeline and the free transports.

Runs without any Cloudflare account: it checks the pieces that must be exactly
right before a real deployment is attempted, namely

  1. the blake3 file hash matches the native implementation (and therefore
     wrangler's hashFile), including the base64+extension subtlety;
  2. the pure-Python fallback equals the native one on chunked inputs;
  3. a manifest built the way pages.push() builds one is JSON-clean and maps
     leading-slash bundle paths to hashes;
  4. every generated link - ws, httpupgrade, xhttp stream-one, trojan, ss -
     round-trips through parse_vless and carries the fields a client needs;
  5. subnet diversity actually leads with one address per /24;
  6. the Pages project name derivation and host format are Pages-safe.

Exit code 0 means everything held.
"""

from __future__ import annotations

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import blake3pure, vless  # noqa: E402

PASS = "\u2705"
FAIL = "\u274c"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{PASS if ok else FAIL} {name}{(' - ' + detail) if detail and not ok else ''}")
    return ok


def native_digest() -> bool:
    import importlib.util

    return importlib.util.find_spec("blake3") is not None



def main() -> int:
    ok = True

    # 1 + 2: blake3 pure vs native, on chunked and parented sizes.
    has_native = native_digest() is not None
    sizes = [0, 1, 63, 64, 65, 1023, 1024, 1025, 2048, 4096, 100_000, 2_097_153]
    for size in sizes:
        data = os.urandom(size)
        pure = blake3pure.digest(data)
        if has_native:
            from blake3 import blake3

            ok = check(f"blake3 pure == native ({size}B)", pure == blake3(data).digest(length=32)) and ok
        elif size == 0:
            # Known vector: blake3 of the empty string.
            ok = check(
                "blake3 empty-string vector",
                blake3pure.hexdigest(b"")
                == "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262",
            ) and ok

    # wrangler hashFile: blake3(base64(contents) + extension), first 32 hex.
    contents = b"worker-module-code"
    b64 = base64.b64encode(contents).decode("ascii")
    expected = blake3pure.hexdigest((b64 + "js").encode("utf-8"))[:32]
    ok = check("file_hash matches base64+extension rule", blake3pure.file_hash("_worker.js", contents) == expected)
    if has_native:
        from blake3 import blake3

        ok = check(
            "file_hash == native blake3",
            blake3pure.file_hash("_worker.js", contents)
            == blake3((b64 + "js").encode("utf-8")).hexdigest()[:32],
        ) and ok

    # 3: manifest shape.
    manifest = {"/_worker.js": blake3pure.file_hash("_worker.js", contents)}
    import json as _json

    round_trip = _json.loads(_json.dumps(manifest))
    ok = check(
        "manifest maps leading-slash paths to 32-char hashes",
        round_trip == manifest
        and all(len(v) == 32 and all(c in "0123456789abcdef" for c in v) for v in round_trip.values()),
    )

    # 4: link round-trips.
    endpoints = [
        {"ip": "104.16.1.2", "port": 443, "latency": 120.0, "jitter": 3.0, "colo": "MRS", "kind": "ip", "verified": True, "range": "104.16.0.0/24"},
        {"ip": "104.16.9.9", "port": 8080, "latency": 300.0, "jitter": 8.0, "colo": "VIE", "kind": "ip", "verified": True, "range": "104.16.0.0/24"},
        {"ip": "2606:4700::6810:201", "port": 2053, "latency": 200.0, "jitter": 4.0, "colo": "AMS", "kind": "ip", "verified": True, "range": "2606:4700::/64"},
    ]
    uuid = vless.new_uuid()
    host = "auto-123456.pages.dev"
    for transport in ("ws", "httpupgrade", "xhttp"):
        links = vless.build_links(uuid, host, endpoints, "AutoVless", transport)
        if transport == "xhttp":
            ok = check(f"{transport}: http endpoints skipped", len(links) == 2) and ok
            links = [link for link in links if link]
        else:
            ok = check(f"{transport}: all endpoints linked", len(links) == 3) and ok
        for link, source in zip(links, [ep for ep in endpoints if not (transport == "xhttp" and not vless.is_tls(ep["port"]))]):
            parsed = vless.parse_vless(link)
            good = (
                parsed["uuid"] == uuid
                and parsed["host"] == host
                and parsed["transport"] == transport
                and (transport != "xhttp" or parsed["mode"] == "stream-one")
                and (transport != "xhttp" or parsed["path"] == "/" + uuid)
                and parsed["security"] == ("tls" if vless.is_tls(parsed["port"]) else "none")
                and parsed["ip"] == str(source["ip"])  # brackets stripped by urlparse, bare address preserved
                and parsed["port"] == int(source["port"])
            )
            ok = check(f"{transport}: {parsed['ip']}:{parsed['port']} round-trips", good) and ok

    mix = vless.all_links(uuid, host, endpoints, "AutoVless")
    ok = check("all_links blends ws + httpupgrade + xhttp", len(mix) == 3 + 3 + 2) and ok

    # 5: subnet diversity.
    bucket = [
        {"ip": "104.16.1.2", "port": 443, "latency": 10.0, "jitter": 0.0, "range": "104.16.0.0/24", "verified": True, "kind": "ip"},
        {"ip": "104.16.1.99", "port": 443, "latency": 11.0, "jitter": 0.0, "range": "104.16.0.0/24", "verified": True, "kind": "ip"},
        {"ip": "104.17.2.3", "port": 443, "latency": 12.0, "jitter": 0.0, "range": "104.17.0.0/24", "verified": True, "kind": "ip"},
        {"ip": "104.17.2.4", "port": 443, "latency": 13.0, "jitter": 0.0, "range": "104.17.0.0/24", "verified": True, "kind": "ip"},
        {"ip": "104.18.3.5", "port": 443, "latency": 14.0, "jitter": 0.0, "range": "104.18.0.0/24", "verified": True, "kind": "ip"},
    ]
    ordered = vless._diversify(bucket)
    heads = [row["ip"] for row in ordered[:3]]
    ok = check(
        "diversify leads with one address per /24",
        heads == ["104.16.1.2", "104.17.2.3", "104.18.3.5"],
        detail=str(heads),
    ) and ok

    # 6: pages naming.
    from bot import pages

    ok = check("project_name is Pages-safe", pages.project_name("auto-123456") == "auto-123456") and ok
    ok = check("pages host format", pages.host_for("auto-123456") == "auto-123456.pages.dev") and ok
    ok = check("is_pages_host", pages.is_pages_host("x.pages.dev") and not pages.is_pages_host("x.workers.dev")) and ok

    print("\n" + ("ALL CHECKS PASSED" if ok else "FAILURES PRESENT"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
