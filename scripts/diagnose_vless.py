#!/usr/bin/env python3
"""Read-only AutoVless/VLESS endpoint diagnostic."""
from __future__ import annotations
import argparse, base64, json, os, re, shutil, socket, sqlite3, ssl, struct, subprocess, time
from pathlib import Path

CRLF = b"\r\n"
DEFAULT_PATH = "/?ed=2560"


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_env(path: Path) -> dict[str, str]:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def docker_env(container: str) -> dict[str, str]:
    raw = run(["docker", "inspect", "--format", "{{json .Config.Env}}", container])
    try:
        return {x.split("=", 1)[0]: x.split("=", 1)[1] for x in json.loads(raw or "[]") if "=" in x}
    except (ValueError, TypeError, IndexError):
        return {}


def short_uuid(value: str) -> str:
    value = str(value or "")
    return value[:8] + "..." + value[-8:] if len(value) > 16 else (value[:4] + "..." if value else "<missing>")


def status_line(raw: bytes) -> tuple[int, str]:
    line = raw.split(b"\n", 1)[0].decode("latin1", "replace").strip()
    m = re.match(r"HTTP/\d(?:\.\d)?\s+(\d{3})(?:\s+(.*))?", line, re.I)
    return (int(m.group(1)), line) if m else (0, line)


def recv_headers(sock: socket.socket) -> tuple[bytes, bytes]:
    data = b""
    while CRLF + CRLF not in data and len(data) < 32768:
        chunk = sock.recv(4096)
        if not chunk: break
        data += chunk
    head, sep, rest = data.partition(CRLF + CRLF)
    return head + sep, rest


def mask_frame(payload: bytes) -> bytes:
    key = os.urandom(4); n = len(payload)
    masked = bytes(x ^ key[i % 4] for i, x in enumerate(payload))
    if n < 126: head = bytes([0x82, 0x80 | n])
    elif n < 65536: head = bytes([0x82, 0xFE]) + struct.pack("!H", n)
    else: head = bytes([0x82, 0xFF]) + struct.pack("!Q", n)
    return head + key + masked


def read_ws_frame(sock: socket.socket, initial: bytes = b"") -> tuple[int, bytes]:
    buf = bytearray(initial)
    def need(n: int) -> None:
        while len(buf) < n:
            chunk = sock.recv(8192)
            if not chunk: raise OSError("peer closed before complete WebSocket frame")
            buf.extend(chunk)
    need(2); b1, b2 = buf[0], buf[1]; del buf[:2]
    opcode, length = b1 & 0x0F, b2 & 0x7F
    if length == 126: need(2); length = struct.unpack("!H", bytes(buf[:2]))[0]; del buf[:2]
    elif length == 127: need(8); length = struct.unpack("!Q", bytes(buf[:8]))[0]; del buf[:8]
    if b2 & 0x80: need(4); mask = bytes(buf[:4]); del buf[:4]
    else: mask = b""
    need(length); payload = bytes(buf[:length]); del buf[:length]
    return opcode, bytes(x ^ mask[i % 4] for i, x in enumerate(payload)) if mask else payload


def vless_probe(sock: socket.socket, uid: str) -> tuple[bool, str]:
    try:
        raw_uuid = bytes.fromhex(uid.replace("-", ""))
        if len(raw_uuid) != 16: return False, "runtime UUID is not 16 bytes"
        target = b"example.com"
        http = b"GET / HTTP/1.1" + CRLF + b"Host: example.com" + CRLF + b"Connection: close" + CRLF + CRLF
        header = b"\x00" + raw_uuid + b"\x00\x01" + struct.pack("!H", 80) + b"\x02" + bytes([len(target)]) + target + http
        sock.sendall(mask_frame(header)); deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            sock.settimeout(max(.2, deadline - time.monotonic()))
            opcode, payload = read_ws_frame(sock)
            if opcode == 8: return False, "WebSocket closed before VLESS response"
            if opcode == 9:
                sock.sendall(bytes([0x8A, len(payload)]) + payload); continue
            if opcode in (0, 1, 2):
                if not payload.startswith(b"\x00\x00"): return False, "received data without VLESS response header"
                if payload[2:]: return True, "VLESS response header and destination traffic received"
                return False, "VLESS response header received without traffic"
        return False, "timeout waiting for VLESS destination traffic"
    except Exception as exc:
        return False, str(exc)


def check_endpoint(index: int, ep: dict, host: str, path: str, uid: str, tls_ports: set[int], timeout: float) -> dict:
    name, port = str(ep.get("ip") or ep.get("host") or ""), int(ep.get("port") or 0)
    r = {"endpoint": f"{name}:{port}", "dns":"FAIL", "tcp":"FAIL", "tls":"N/A", "sni":"N/A", "http":"FAIL", "ws":"FAIL", "status":0, "vless":"N/A", "traffic":"N/A", "latency":None, "reason":""}
    started = time.perf_counter(); sock = None
    try:
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(name, port, type=socket.SOCK_STREAM)))
        if not addresses: raise OSError("DNS returned no addresses")
        r["dns"] = "PASS"; sock = socket.create_connection((addresses[0], port), timeout=timeout); r["tcp"] = "PASS"
        if port in tls_ports:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host); r["tls"] = r["sni"] = "PASS"
        sock.settimeout(timeout); key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path or '/'} HTTP/1.1" + CRLF.decode() + f"Host: {host}" + CRLF.decode() + "Connection: Upgrade" + CRLF.decode() + "Upgrade: websocket" + CRLF.decode() + f"Sec-WebSocket-Key: {key}" + CRLF.decode() + "Sec-WebSocket-Version: 13" + CRLF.decode() + "User-Agent: AutoVless-Diagnostic/1" + CRLF.decode() + CRLF.decode()).encode("ascii")
        sock.sendall(req); headers, _ = recv_headers(sock); code, line = status_line(headers); r["status"] = code; r["http"] = "PASS" if code else "FAIL"
        if code != 101: r["reason"] = line or "no HTTP status line"; return r
        r["ws"] = "PASS"; r["latency"] = round((time.perf_counter() - started) * 1000, 1)
        ok, why = vless_probe(sock, uid); r["vless"] = r["traffic"] = "PASS" if ok else "FAIL"; r["reason"] = why
    except ssl.SSLCertVerificationError as exc:
        r["tls"] = r["sni"] = "FAIL"; r["reason"] = f"certificate/SNI verification: {exc.reason}"
    except ssl.SSLError as exc:
        r["tls"] = r["sni"] = "FAIL"; r["reason"] = f"TLS/SNI: {exc}"
    except (socket.timeout, TimeoutError): r["reason"] = "timeout"
    except Exception as exc: r["reason"] = str(exc)
    finally:
        if sock:
            try: sock.close()
            except OSError: pass
    return r


def source_default(root: Path) -> str:
    p = root / "worker" / "vless-worker.js"
    try: text = p.read_text(encoding="utf-8")
    except OSError: text = ""
    m = re.search(r"(?:WS_PATH|wsPath)\s*[:=].{0,80}?['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else DEFAULT_PATH


def load_panels(path: Path) -> list[dict]:
    if not path.exists(): return []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True); con.row_factory = sqlite3.Row
        rows = con.execute("SELECT host,uuid,endpoints,healthy FROM panels ORDER BY updated_at DESC").fetchall(); con.close()
        out = []
        for x in rows:
            try: eps = json.loads(x["endpoints"] or "[]")
            except ValueError: eps = []
            out.append({"host":x["host"], "uuid":x["uuid"], "endpoints":eps, "healthy":x["healthy"]})
        return out
    except Exception as exc:
        print(f"DB: FAIL (read-only query failed: {exc})"); return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only AutoVless endpoint diagnostic")
    ap.add_argument("--root", default="/opt/autovless"); ap.add_argument("--container", default="autovless"); ap.add_argument("--db", default=""); ap.add_argument("--panel", default=""); ap.add_argument("--timeout", type=float, default=8.0)
    a = ap.parse_args(); root = Path(a.root).resolve(); env = parse_env(root / ".env"); env.update(docker_env(a.container))
    db = Path(a.db or env.get("DB_PATH") or root / "data" / "autovless.db"); default = source_default(root); panels = load_panels(db)
    if a.panel: panels = [p for p in panels if p["host"].lower() == a.panel.lower() or p["uuid"].lower().startswith(a.panel.lower())]
    print("AutoVless read-only VLESS diagnostic"); print(f"Root: {root}\nContainer: {a.container}\nDB: {db} (read-only)\nWorker source: {root / 'worker' / 'vless-worker.js'}"); print(f"Docker available: {'PASS' if shutil.which('docker') else 'FAIL'}"); print("Secrets: redacted; no Cloudflare API calls or writes performed")
    if not panels: print("Panels: NONE FOUND. Check --root/--db."); return 2
    tls_ports = {int(x) for x in re.split(r"[,;\s]+", env.get("TLS_PORTS", "443,2053,8443")) if x.isdigit()}
    for n, p in enumerate(panels, 1):
        host, uid, path = str(p["host"]), str(p["uuid"]), env.get("WS_PATH", "") or default
        print(f"\nPanel #{n}: host={host} uuid={short_uuid(uid)} healthy_field={bool(p['healthy'])}"); print(f"Worker URL: https://{host}/{short_uuid(uid)}/health"); print(f"Config WS_PATH: {path}"); print(f"Worker source default path: {default}"); print(f"UUID source: panel DB {short_uuid(uid)}; Worker binding UUID not printed")
        if path != default: print("CONFIG WARNING: runtime WS_PATH differs from Worker source default; verify binding")
        for i, ep in enumerate(p["endpoints"], 1):
            r = check_endpoint(i, ep, host, path, uid, tls_ports, a.timeout); print(f"\nEndpoint #{i} {r['endpoint']}"); print(f"DNS: {r['dns']}\nTCP: {r['tcp']}\nTLS: {r['tls']}\nSNI: {r['sni']}\nHTTP: {r['http']}\nWS: {r['ws']}\nStatus: {r['status'] or 'n/a'}"); print(f"VLESS: {r['vless']}\nTraffic: {r['traffic']}\nLatency: {r['latency'] if r['latency'] is not None else 'n/a'} ms"); print(f"Final: {'HEALTHY' if r['vless'] == 'PASS' and r['traffic'] == 'PASS' else 'UNHEALTHY'}");
            if r["reason"]: print(f"Reason: {r['reason']}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
