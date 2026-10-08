#!/usr/bin/env python3
"""Read-only AutoVless/VLESS endpoint diagnostic.

No Cloudflare API calls, deployments, writes, or secret output. Uses only local
Docker metadata, .env names, the SQLite panel rows, Worker source, DNS, TCP,
TLS/SNI, HTTP/WebSocket upgrade, and a small real VLESS-over-WS traffic probe.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PATH = "/?ed=2560"
SECRET_WORDS = ("TOKEN", "SECRET", "PASSWORD", "PASS", "PRIVATE", "KEY", "AUTH", "LICENSE", "CREDENTIAL")


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def docker_env(container: str) -> dict[str, str]:
    raw = run(["docker", "inspect", "--format", "{{json .Config.Env}}", container])
    try:
        return {str(x).split("=", 1)[0]: str(x).split("=", 1)[1] for x in json.loads(raw or "[]") if "=" in str(x)}
    except (ValueError, TypeError, IndexError):
        return {}


def short_uuid(value: str) -> str:
    value = str(value or "")
    return value[:8] + "..." + value[-8:] if len(value) > 16 else (value[:4] + "..." if value else "<missing>")


def safe_url(host: str, uuid: str, path: str) -> str:
    return f"https://{host}/{short_uuid(uuid)}{path}"


def status_line(raw: bytes) -> tuple[int, str]:
    line = raw.split(b"\\n", 1)[0].decode("latin1", "replace").strip()
    m = re.match(r"HTTP/\\d(?:\\.\\d)?\\s+(\\d{3})(?:\\s+(.*))?", line, re.I)
    return (int(m.group(1)), line) if m else (0, line)


def recv_headers(sock: socket.socket, limit: int = 32768) -> tuple[bytes, bytes]:
    data = b""
    while b"\\r\\n\\r\\n" not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, sep, rest = data.partition(b"\\r\\n\\r\\n")
    return head + (sep or b""), rest


def mask_frame(payload: bytes) -> bytes:
    key = os.urandom(4)
    masked = bytes(x ^ key[i % 4] for i, x in enumerate(payload))
    n = len(payload)
    if n < 126:
        head = bytes([0x82, 0x80 | n])
    elif n < 65536:
        head = bytes([0x82, 0x80 | 126]) + struct.pack("!H", n)
    else:
        head = bytes([0x82, 0x80 | 127]) + struct.pack("!Q", n)
    return head + key + masked


def read_ws_frame(sock: socket.socket, initial: bytes = b"") -> tuple[int, bytes]:
    buf = bytearray(initial)
    def need(n: int) -> None:
        while len(buf) < n:
            chunk = sock.recv(8192)
            if not chunk:
                raise OSError("peer closed before complete WebSocket frame")
            buf.extend(chunk)
    need(2)
    b1, b2 = buf[0], buf[1]
    del buf[:2]
    opcode, length = b1 & 0x0F, b2 & 0x7F
    if length == 126:
        need(2); length = struct.unpack("!H", bytes(buf[:2]))[0]; del buf[:2]
    elif length == 127:
        need(8); length = struct.unpack("!Q", bytes(buf[:8]))[0]; del buf[:8]
    if b2 & 0x80:
        need(4); mask = bytes(buf[:4]); del buf[:4]
    else:
        mask = b""
    need(length)
    payload = bytes(buf[:length]); del buf[:length]
    if mask:
        payload = bytes(x ^ mask[i % 4] for i, x in enumerate(payload))
    return opcode, payload


def vless_probe(sock: socket.socket, uid: str) -> tuple[bool, str]:
    try:
        raw_uuid = bytes.fromhex(uid.replace("-", ""))
        if len(raw_uuid) != 16:
            return False, "runtime UUID is not 16 bytes"
        target = b"example.com"
        request = b"GET / HTTP/1.1\\r\\nHost: example.com\\r\\nConnection: close\\r\\n\\r\\n"
        header = b"\\x00" + raw_uuid + b"\\x00\\x01" + struct.pack("!H", 80) + b"\\x02" + bytes([len(target)]) + target + request
        sock.sendall(mask_frame(header))
        deadline = time.monotonic() + 8
        data = b""
        while time.monotonic() < deadline:
            sock.settimeout(max(0.2, deadline - time.monotonic()))
            opcode, payload = read_ws_frame(sock, data)
            data = b""
            if opcode == 0x8:
                return False, "WebSocket closed before a VLESS response"
            if opcode == 0x9:
                sock.sendall(bytes([0x8A, len(payload)]) + payload)
                continue
            if opcode in (0x1, 0x2, 0x0):
                if payload.startswith(b"\\x00\\x00"):
                    traffic = payload[2:]
                    if traffic.startswith(b"HTTP/") or traffic:
                        return True, "VLESS response header and destination traffic received"
                    return False, "VLESS response header received without traffic"
                return False, "received data without VLESS response header"
        return False, "timeout waiting for VLESS destination traffic"
    except Exception as exc:  # diagnostic must continue with the next endpoint
        return False, str(exc)


def check_endpoint(index: int, endpoint: dict, host: str, path: str, uid: str, tls_ports: set[int], timeout: float) -> dict:
    ip_or_host, port = str(endpoint.get("ip") or endpoint.get("host") or ""), int(endpoint.get("port") or 0)
    result = {"index": index, "endpoint": f"{ip_or_host}:{port}", "dns": "FAIL", "tcp": "FAIL", "tls": "N/A", "sni": "N/A", "http": "FAIL", "ws": "FAIL", "status": 0, "vless": "N/A", "traffic": "N/A", "latency_ms": None, "reason": ""}
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(ip_or_host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(item[4][0] for item in infos))
        if not addresses:
            raise OSError("DNS returned no addresses")
        result["dns"] = "PASS"
        connect_host = addresses[0]
        sock = socket.create_connection((connect_host, port), timeout=timeout)
        result["tcp"] = "PASS"
        secure = port in tls_ports
        if secure:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
            result["tls"] = "PASS"
            result["sni"] = "PASS"
        else:
            result["tls"] = "N/A"
            result["sni"] = "N/A"
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {path or '/'} HTTP/1.1\\r\\nHost: {host}\\r\\n"
                   "Connection: Upgrade\\r\\nUpgrade: websocket\\r\\n"
                   f"Sec-WebSocket-Key: {key}\\r\\nSec-WebSocket-Version: 13\\r\\n"
                   "User-Agent: AutoVless-Diagnostic/1\\r\\n\\r\\n").encode("ascii")
        sock.sendall(request)
        headers, remainder = recv_headers(sock)
        code, line = status_line(headers)
        result["status"] = code
        result["http"] = "PASS" if code else "FAIL"
        if code != 101:
            result["reason"] = line or "no HTTP status line"
            sock.close(); return result
        result["ws"] = "PASS"
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        ok, why = vless_probe(sock, uid)
        result["vless"] = "PASS" if ok else "FAIL"
        result["traffic"] = "PASS" if ok else "FAIL"
        result["reason"] = why
        sock.close()
    except ssl.SSLCertVerificationError as exc:
        result["tls"] = "FAIL"; result["sni"] = "FAIL"; result["reason"] = f"certificate/SNI verification: {exc.reason}"
    except ssl.SSLError as exc:
        result["tls"] = "FAIL"; result["sni"] = "FAIL"; result["reason"] = f"TLS/SNI: {exc}"
    except (socket.timeout, TimeoutError):
        result["reason"] = "timeout"
    except Exception as exc:
        result["reason"] = str(exc)
    return result


def worker_defaults(root: Path) -> tuple[str, str]:
    source = root / "worker" / "vless-worker.js"
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    m = re.search(r"(?:WS_PATH|wsPath)\\s*[:=].{0,80}?['\"]([^'\"]+)['\"]", text)
    return (m.group(1) if m else DEFAULT_PATH, str(source))


def load_panels(db_path: Path) -> list[dict]:
    if not db_path.exists(): return []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT tg_id,host,uuid,endpoints,healthy,updated_at FROM panels ORDER BY updated_at DESC").fetchall()
        con.close()
        out = []
        for row in rows:
            try: eps = json.loads(row["endpoints"] or "[]")
            except ValueError: eps = []
            out.append({"tg_id": row["tg_id"], "host": row["host"], "uuid": row["uuid"], "endpoints": eps, "healthy": row["healthy"], "updated_at": row["updated_at"]})
        return out
    except Exception as exc:
        print(f"DB: FAIL (read-only open/query failed: {exc})")
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only AutoVless endpoint diagnostic")
    ap.add_argument("--root", default="/opt/autovless")
    ap.add_argument("--container", default="autovless")
    ap.add_argument("--db", default="")
    ap.add_argument("--panel", default="", help="panel host or UUID prefix; default: all panels")
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    env = parse_env(root / ".env")
    env.update({k: v for k, v in docker_env(args.container).items() if k not in {"PATH", "TZ", "DATA_DIR"}})
    db_path = Path(args.db or env.get("DB_PATH") or root / "data" / "autovless.db")
    source_path = root / "worker" / "vless-worker.js"
    source_default, _ = worker_defaults(root)
    panels = load_panels(db_path)
    if args.panel:
        panels = [p for p in panels if str(p["host"]).lower() == args.panel.lower() or str(p["uuid"]).lower().startswith(args.panel.lower())]
    print("AutoVless read-only VLESS diagnostic")
    print(f"Root: {root}\nContainer: {args.container}\nDB: {db_path} (read-only)\nWorker source: {source_path}")
    print(f"Docker available: {'PASS' if shutil.which('docker') else 'FAIL'}")
    print("Secrets: redacted; no Cloudflare API calls or writes performed")
    if not panels:
        print("Panels: NONE FOUND. Run this from the VPS with the correct --root/--db.")
        return 2
    tls_ports = {int(x) for x in re.split(r"[,;\\s]+", env.get("TLS_PORTS", "443,2053,8443")) if x.isdigit()}
    for pnum, panel in enumerate(panels, 1):
        host, uid = str(panel["host"]), str(panel["uuid"])
        runtime_path = env.get("WS_PATH", "") or source_default
        print(f"\\nPanel #{pnum}: host={host} uuid={short_uuid(uid)} healthy_field={bool(panel['healthy'])}")
        print(f"Worker URL: {safe_url(host, uid, '/health')} (UUID redacted)")
        print(f"Config: WS_PATH={runtime_path} TLS_PORTS={','.join(map(str, sorted(tls_ports)))}")
        print(f"Worker source default path: {source_default}")
        print(f"UUID source: panel DB UUID {short_uuid(uid)}; Worker binding UUID is not printed")
        if runtime_path != source_default:
            print("CONFIG WARNING: runtime WS_PATH differs from Worker source default; verify binding")
        for i, ep in enumerate(panel["endpoints"], 1):
            r = check_endpoint(i, ep, host, runtime_path, uid, tls_ports, args.timeout)
            print(f"\\nEndpoint #{i} {r['endpoint']}")
            print(f"DNS: {r['dns']}\\nTCP: {r['tcp']}\\nTLS: {r['tls']}\\nSNI: {r['sni']}\\nHTTP: {r['http']}\\nWS: {r['ws']}\\nStatus: {r['status'] or 'n/a'}")
            print(f"VLESS: {r['vless']}\\nTraffic: {r['traffic']}\\nLatency: {r['latency_ms'] if r['latency_ms'] is not None else 'n/a'} ms")
            print(f"Final: {'HEALTHY' if r['vless'] == 'PASS' and r['traffic'] == 'PASS' else 'UNHEALTHY'}")
            if r["reason"]: print(f"Reason: {r['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
