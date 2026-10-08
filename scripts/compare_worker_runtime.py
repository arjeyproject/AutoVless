#!/usr/bin/env python3
"""Read-only comparison of two AutoVless Worker runtimes.

Uses public HTTP probes plus optional local Cloudflare API metadata. It never
prints tokens, secrets, private keys, full UUIDs, binding values, or Worker
source. Cloudflare API access is read-only and uses only an already-present
local environment token.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, socket, sqlite3, ssl, subprocess, sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_WORKER = "worker/vless-worker.js"
SECRET_KEYS = re.compile(r"token|secret|password|private|license|credential|auth|key", re.I)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.I)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short(value: object) -> str:
    text = str(value or "")
    if len(text) <= 16: return "<set>" if text else "<missing>"
    return text[:8] + "..." + text[-8:]


def redact_key(name: str) -> str:
    return "<redacted>" if SECRET_KEYS.search(name) else "<set>"


def env_file(path: Path) -> dict[str, str]:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError: pass
    return out


def db_panels(path: Path) -> dict[str, dict]:
    if not path.exists(): return {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True); con.row_factory = sqlite3.Row
        rows = con.execute("SELECT host,uuid,account_id,script_name,healthy,updated_at FROM panels").fetchall(); con.close()
        return {str(r["host"]).lower(): dict(r) for r in rows}
    except Exception as exc:
        print(f"DB_READ_ERROR: {type(exc).__name__}: {exc}"); return {}


def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 15) -> tuple[int, dict[str, str], bytes]:
    try:
        req = Request(url, headers=headers or {}, method="GET")
        with urlopen(req, timeout=timeout) as r: return int(r.status), dict(r.headers.items()), r.read(8_000_000)
    except HTTPError as e:
        return int(e.code), dict(e.headers.items()), e.read(4096)
    except (URLError, TimeoutError, OSError) as e:
        return 0, {}, f"LOCAL_ERROR:{type(e).__name__}:{e}".encode()


def public(host: str, uuid: str) -> dict:
    result = {"host": host, "health": None, "root": None, "health_body_sha256": None, "root_body_sha256": None}
    for label, path in (("health", f"https://{host}/{uuid}/health"), ("root", f"https://{host}/")):
        code, headers, body = http_get(path)
        text = body.decode("utf-8", "replace")
        result[label] = {"status": code, "content_type": headers.get("Content-Type", ""), "error_1101": "1101" in text, "body_preview": text[:120].replace("\n", " ") if code not in (200, 500) else "<suppressed>"}
        result[label + "_body_sha256"] = sha256_bytes(body)
    return result


def api_get(base: str, account: str, script: str, endpoint: str, token: str) -> tuple[int, object]:
    url = f"{base}/accounts/{account}/workers/scripts/{script}/{endpoint.lstrip('/')}"
    code, _, body = http_get(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try: return code, json.loads(body.decode("utf-8", "replace"))
    except Exception: return code, {"raw_sha256": sha256_bytes(body), "raw_bytes": len(body)}


def metadata(api: str, panel: dict, token: str) -> dict:
    if not token: return {"available": False, "reason": "no local API token found"}
    account, script = str(panel.get("account_id") or ""), str(panel.get("script_name") or "")
    if not account or not script: return {"available": False, "reason": "account_id/script_name missing from local DB"}
    out = {"available": True, "account_id": short(account), "script_name": script}
    for label, endpoint in (("settings", "settings"), ("deployments", "deployments"), ("versions", "versions"), ("content", "content")):
        code, data = api_get(api, account, script, endpoint, token)
        if label == "content":
            if isinstance(data, dict): out[label] = {"status": code, "sha256": data.get("raw_sha256"), "bytes": data.get("raw_bytes"), "source_downloaded": code == 200}
            else: out[label] = {"status": code, "source_downloaded": False, "value_type": type(data).__name__}
            continue
        if isinstance(data, dict):
            safe = {}
            for k, v in data.items():
                if SECRET_KEYS.search(str(k)): safe[k] = "<redacted>"
                elif isinstance(v, (dict, list)) and k.lower() in {"bindings", "env", "environment", "settings"}: safe[k] = summarize(v)
                else: safe[k] = v if not isinstance(v, str) or len(v) < 300 else short(v)
            out[label] = {"status": code, "data": safe}
        else: out[label] = {"status": code, "type": type(data).__name__}
    return out


def summarize(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): ("<redacted>" if SECRET_KEYS.search(str(k)) else summarize(v)) for k, v in value.items()}
    if isinstance(value, list): return [summarize(x) for x in value[:50]]
    if isinstance(value, str):
        if UUID_RE.match(value): return short(value)
        return "<set>" if len(value) > 80 else value
    return value


def source_facts(path: Path) -> dict:
    try: raw = path.read_bytes(); text = raw.decode("utf-8")
    except OSError as exc: return {"exists": False, "error": str(exc)}
    imports = re.findall(r"^\s*import\s+.+?from\s+['\"](.+?)['\"]", text, re.M)
    top = []
    for line in text.splitlines():
        if line.startswith(("const ", "let ", "var ", "function ", "export ")): top.append(line[:180])
    return {"exists": True, "sha256": sha256_bytes(raw), "bytes": len(raw), "module_format": "ES module" if "export default" in text else "unknown", "imports": imports, "compatibility_date_in_source": re.findall(r"compatibility.?date[^\n]{0,80}", text, re.I), "top_level_declarations_count": len(top), "uuid_binding_references": len(re.findall(r"UUID|uuidBytes|uuidToBytes", text)), "ws_path_literals": sorted(set(re.findall(r"/\?ed=[0-9]+|/ss", text))), "top_level_preview": top[:20]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Golden vs Broken Worker runtime comparison")
    ap.add_argument("--root", default="/opt/autovless"); ap.add_argument("--db", default=""); ap.add_argument("--golden", default="i4f1565d14.prostoreshop.site"); ap.add_argument("--broken", default="auto-524730.zeus-gltgwi.workers.dev"); ap.add_argument("--api", default="https://api.cloudflare.com/client/v4"); ap.add_argument("--token-env", default="CLOUDFLARE_API_TOKEN")
    a = ap.parse_args(); root = Path(a.root).resolve(); env = env_file(root / ".env"); token = os.getenv(a.token_env) or env.get(a.token_env, "")
    db = Path(a.db or env.get("DB_PATH") or root / "data" / "autovless.db"); panels = db_panels(db); worker = source_facts(root / REPO_WORKER)
    print("AutoVless read-only Worker runtime comparison"); print(f"Repository: {root}\nDatabase: {db} (read-only)\nAPI token: {'available locally, never printed' if token else 'not found; public comparison only'}")
    print("\nREPOSITORY SOURCE:"); print(json.dumps(worker, indent=2, ensure_ascii=False))
    records = {}
    for label, host in (("GOLDEN", a.golden), ("BROKEN", a.broken)):
        panel = panels.get(host.lower(), {}); uid = str(panel.get("uuid") or "")
        print(f"\n{label}:"); print(f"host={host}\nlocal_panel_found={bool(panel)}\nuuid={short(uid)}\nhealthy_field={panel.get('healthy', '<missing>')}\naccount_id={short(panel.get('account_id'))}\nscript_name={panel.get('script_name', '<missing>')}")
        print("PUBLIC_RUNTIME:"); print(json.dumps(public(host, uid), indent=2, ensure_ascii=False))
        print("CLOUDFLARE_METADATA:"); print(json.dumps(metadata(a.api, panel, token), indent=2, ensure_ascii=False))
        records[label] = {"panel": panel, "public": public(host, uid), "metadata": metadata(a.api, panel, token)}
    print("\nDIFF:")
    for field in ("account_id", "script_name", "healthy"):
        print(f"{field}: GOLDEN={short(records['GOLDEN']['panel'].get(field))} BROKEN={short(records['BROKEN']['panel'].get(field))}")
    print("source_hash_current_main=" + str(worker.get("sha256")))
    print("\nROOT_CAUSE_STATUS: UNKNOWN_UNTIL_DEPLOYED_METADATA_OR_SOURCE_IS_AVAILABLE")
    print("No deployments, writes, redeploys, or configuration changes were performed.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
