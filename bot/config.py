"""Runtime configuration, loaded once from the environment."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
TLS_PORTS = (443, 2053, 2083, 2087, 2096, 8443)
HTTP_PORTS = (80, 8080, 8880, 2052, 2082, 2086, 2095)
# More than one port per group on purpose: a single filtered port must never be
# able to take out every TLS config a user holds.
DEFAULT_TLS_PORTS = (443, 2053, 8443)
DEFAULT_HTTP_PORTS = (80, 8080)
DEFAULT_CLEAN_SOURCES = ("https://ipdb.api.030101.xyz/?type=bestcf", "https://raw.githubusercontent.com/ymyuuu/IPDB/main/bestcf.txt")
DEFAULT_CLEAN_FILES = ("endpoints/clean-ips.txt",)
DEFAULT_CLEAN_DOMAINS = ("cf.090227.xyz", "cdn.xn--b6gac.eu.org", "cf.877774.xyz", "cfip.cfcdn.eu.org")
DEFAULT_PROXY_SOURCES = ("https://ipdb.api.030101.xyz/?type=bestproxy", "https://raw.githubusercontent.com/ymyuuu/IPDB/main/bestproxy.txt")
DEFAULT_PROXY_SEEDS = ("proxyip.fxxk.dedyn.io", "proxyip.aliyun.fxxk.dedyn.io", "proxyip.oracle.fxxk.dedyn.io", "proxyip.digitalocean.fxxk.dedyn.io", "cdn.xn--b6gac.eu.org", "cdn-all.xn--b6gac.eu.org", "bpb.yousef.isegaro.com", "edgetunnel.anycast.eu.org")

def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()

def _int(name: str, default: int) -> int:
    try: return int(_str(name) or default)
    except ValueError: return default

def _float(name: str, default: float) -> float:
    try: return float(_str(name) or default)
    except ValueError: return default

def _bool(name: str, default: bool) -> bool:
    raw = _str(name).lower()
    return default if not raw else raw in {"1", "true", "yes", "on"}

def _list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = _str(name)
    if not raw: return default
    return tuple(dict.fromkeys(x.strip() for x in raw.replace(";", ",").replace("\n", ",").split(",") if x.strip()))

def _ids(name: str) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(x.strip()) for x in _str(name).replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()))

def _int_list(name: str, default: tuple[int, ...] = ()) -> tuple[int, ...]:
    raw = _str(name)
    if not raw: return default
    values = tuple(dict.fromkeys(int(x) for x in raw.replace(";", ",").split(",") if x.strip().isdigit()))
    return values or default

def _ports(name: str, default: tuple[int, ...], allowed: tuple[int, ...]) -> tuple[int, ...]:
    values = tuple(x for x in _int_list(name, default) if x in allowed)
    return values or default

@dataclass(frozen=True)
class Settings:
    bot_token: str; admin_ids: tuple[int, ...]; secret_key: str
    data_dir: Path; db_path: Path; worker_file: Path; sweep_state: Path
    brand: str; support_url: str; channel_url: str; donate_url: str; github_url: str; webapp_url: str; default_lang: str
    tls_ports: tuple[int, ...]; http_ports: tuple[int, ...]; tls_config_count: int; http_config_count: int
    scan_interval: int; scan_batch: int; scan_concurrency: int; scan_timeout: float
    verify_top: int; verify_probes: int; scan_rounds: int; scan_waves: int; scan_min_verified: int
    verify_ws: bool; verify_host: str; accept_timeout: float; accept_retries: int
    scan_ttl: int; stale_factor: int; sweep_per_subnet: int; pool_size: int; pool_target: int
    clean_ip_sources: tuple[str, ...]; clean_ip_files: tuple[str, ...]; clean_domains: tuple[str, ...]
    source_ttl: int; source_retry: int; seed_limit: int; max_fails: int
    proxy_ip: str; proxy_seeds: tuple[str, ...]; proxy_sources: tuple[str, ...]; proxy_ports: tuple[int, ...]
    proxy_scan_interval: int; proxy_scan_limit: int; proxy_pool_size: int; proxy_per_panel: int; relay_strikes: int
    dns_server: str; fallback_host: str; health_attempts: int; sub_sources: tuple[str, ...]; sub_refresh: int
    autopilot: bool; autopilot_interval: int; autopilot_batch: int; autopilot_max_age: int
    curator: bool; curator_interval: int; curator_batch: int; curator_rounds: int; curator_required: int
    curator_recheck: int; curator_strikes: int; curator_floor: float; curator_min_samples: int
    curator_stale: int; curator_abort_ratio: float; curator_push: bool; curator_push_batch: int
    warp_enabled: bool; warp_amnezia: bool; warp_mtu: int; warp_dns: str; warp_license: str; warp_ports: tuple[int, ...]
    warp_scan_interval: int; warp_scan_sample: int; warp_scan_concurrency: int; warp_scan_timeout: float
    warp_scan_attempts: int; warp_verify_top: int; warp_pool_size: int; warp_per_config: int
    store_tokens: bool; request_timeout: float; log_level: str
    compatibility_date: str = "2024-11-01"; languages: tuple[str, ...] = field(default=("fa", "en"))
    @property
    def config_count(self) -> int: return self.tls_config_count + self.http_config_count
    @property
    def all_ports(self) -> tuple[int, ...]: return tuple(dict.fromkeys(self.tls_ports + self.http_ports))
    def is_admin(self, tg_id: int) -> bool: return tg_id in self.admin_ids

def load_settings() -> Settings:
    data = Path(_str("DATA_DIR", str(BASE_DIR / "data"))); data.mkdir(parents=True, exist_ok=True)
    secret = _str("SECRET_KEY"); key = data / ".secret"
    if not secret:
        if key.exists(): secret = key.read_text(encoding="utf-8").strip()
        else:
            secret = secrets.token_urlsafe(48); key.write_text(secret, encoding="utf-8"); key.chmod(0o600)
    lang = _str("DEFAULT_LANG", "fa").lower(); lang = lang if lang in {"fa", "en"} else "fa"
    proxy_ip = _str("PROXY_IP"); clean = _list("CLEAN_IP_SOURCES", DEFAULT_CLEAN_SOURCES)
    curator_rounds = max(2, min(5, _int("CURATOR_ROUNDS", 3)))
    return Settings(
        bot_token=_str("BOT_TOKEN"), admin_ids=_ids("ADMIN_IDS"), secret_key=secret, data_dir=data,
        db_path=Path(_str("DB_PATH", str(data / "autovless.db"))),
        # vless-worker.js is the stable, battle-tested bundle. v2 remains in the repo for comparison.
        worker_file=Path(_str("WORKER_FILE", str(BASE_DIR / "worker" / "vless-worker.js"))),
        sweep_state=Path(_str("SWEEP_STATE", str(data / "clean-sweep.json"))), brand=_str("BRAND", "AutoVless"),
        support_url=_str("SUPPORT_URL", "https://t.me/AutoVless"), channel_url=_str("CHANNEL_URL", "https://t.me/AutoVless"),
        donate_url=_str("DONATE_URL"), github_url=_str("GITHUB_URL", "https://github.com/arjeyproject/AutoVless"), webapp_url=_str("WEBAPP_URL"), default_lang=lang,
        tls_ports=_ports("TLS_PORTS", DEFAULT_TLS_PORTS, TLS_PORTS), http_ports=_ports("HTTP_PORTS", DEFAULT_HTTP_PORTS, HTTP_PORTS),
        tls_config_count=max(0, _int("TLS_CONFIG_COUNT", 6)), http_config_count=max(0, _int("HTTP_CONFIG_COUNT", 3)),
        scan_interval=max(60, _int("SCAN_INTERVAL", 480)), scan_batch=max(128, _int("SCAN_BATCH", 1600)), scan_concurrency=max(16, _int("SCAN_CONCURRENCY", 192)),
        scan_timeout=max(.3, _int("SCAN_TIMEOUT_MS", 1400) / 1000), verify_top=max(8, _int("VERIFY_TOP", 48)), verify_probes=max(2, min(5, _int("VERIFY_PROBES", 3))),
        scan_rounds=max(2, min(5, _int("SCAN_ROUNDS", 3))), scan_waves=max(1, min(5, _int("SCAN_WAVES", 4))), scan_min_verified=max(4, _int("SCAN_MIN_VERIFIED", 12)),
        # A TLS endpoint is only verified by a real WebSocket upgrade against a
        # real panel hostname. VERIFY_HOST pins that hostname; left blank, the
        # newest live panel is used and a cold pool falls back to the weaker
        # trace check until the first panel exists.
        verify_ws=_bool("VERIFY_WS", True), verify_host=_str("VERIFY_HOST").lower(),
        accept_timeout=max(2.0, _int("ACCEPT_TIMEOUT_MS", 8000) / 1000), accept_retries=max(0, min(4, _int("ACCEPT_RETRIES", 2))),
        scan_ttl=max(300, _int("SCAN_TTL", 3600)), stale_factor=max(2, _int("STALE_FACTOR", 8)), sweep_per_subnet=max(1, min(8, _int("SWEEP_PER_SUBNET", 2))),
        # POOL_SIZE is the whole pool's budget; POOL_TARGET is the floor every
        # single port is kept at, in fresh verified rows. The trim never takes a
        # port below the target, so growing the pool is not undone by the sweep
        # that follows.
        pool_size=max(24, _int("POOL_SIZE", 720)), pool_target=max(8, _int("POOL_TARGET", 40)),
        clean_ip_sources=clean, clean_ip_files=_list("CLEAN_IP_FILES", DEFAULT_CLEAN_FILES), clean_domains=_list("CLEAN_DOMAINS", DEFAULT_CLEAN_DOMAINS),
        source_ttl=max(300, _int("SOURCE_TTL", 1800)), source_retry=max(60, _int("SOURCE_RETRY", 180)), seed_limit=max(50, _int("SEED_LIMIT", 800)), max_fails=max(1, _int("MAX_FAILS", 3)),
        proxy_ip=proxy_ip, proxy_seeds=_list("PROXY_IP", DEFAULT_PROXY_SEEDS), proxy_sources=_list("PROXY_IP_SOURCES", DEFAULT_PROXY_SOURCES), proxy_ports=_ports("PROXY_PORTS", (443,), TLS_PORTS), proxy_scan_interval=max(300, _int("PROXY_SCAN_INTERVAL", 1200)), proxy_scan_limit=max(32, _int("PROXY_SCAN_LIMIT", 500)), proxy_pool_size=max(8, _int("PROXY_POOL_SIZE", 80)), proxy_per_panel=max(2, _int("PROXY_PER_PANEL", 6)),
        relay_strikes=max(2, _int("RELAY_STRIKES", 3)),
        dns_server=_str("DNS_SERVER", "8.8.8.8"), fallback_host=_str("FALLBACK_HOST", "www.wikipedia.org"), health_attempts=max(2, _int("HEALTH_ATTEMPTS", 8)), sub_sources=_list("SUB_SOURCES", clean), sub_refresh=max(60, _int("SUB_REFRESH", 180)),
        autopilot=_bool("AUTOPILOT", True), autopilot_interval=max(120, _int("AUTOPILOT_INTERVAL", 600)), autopilot_batch=max(1, _int("AUTOPILOT_BATCH", 8)), autopilot_max_age=max(600, _int("AUTOPILOT_MAX_AGE", 10800)),
        # The curator rechecks stored addresses on the client's own path and
        # deletes what stops answering. CURATOR_STRIKES consecutive misses, or a
        # reliability under CURATOR_FLOOR once there are enough samples, or
        # nothing confirmed for CURATOR_STALE seconds, and the row is gone.
        # CURATOR_ABORT is the safety valve: if that share of a batch misses,
        # the box or the reference panel is the problem, so nothing is purged.
        curator=_bool("CURATOR", True), curator_interval=max(60, _int("CURATOR_INTERVAL", 300)),
        curator_batch=max(16, _int("CURATOR_BATCH", 160)), curator_rounds=curator_rounds,
        curator_required=max(1, min(curator_rounds, _int("CURATOR_REQUIRED", 2))),
        curator_recheck=max(120, _int("CURATOR_RECHECK", 900)), curator_strikes=max(2, _int("CURATOR_STRIKES", 3)),
        curator_floor=min(0.9, max(0.05, _float("CURATOR_FLOOR", 0.4))), curator_min_samples=max(2, _int("CURATOR_MIN_SAMPLES", 5)),
        curator_stale=max(1800, _int("CURATOR_STALE", 14400)), curator_abort_ratio=min(1.0, max(0.5, _float("CURATOR_ABORT", 0.85))),
        curator_push=_bool("CURATOR_PUSH", True), curator_push_batch=max(1, _int("CURATOR_PUSH_BATCH", 6)),
        warp_enabled=_bool("WARP_ENABLED", True), warp_amnezia=_bool("WARP_AMNEZIA", True), warp_mtu=max(1000, min(1420, _int("WARP_MTU", 1280))), warp_dns=_str("WARP_DNS", "1.1.1.1, 1.0.0.1"), warp_license=_str("WARP_LICENSE"), warp_ports=_int_list("WARP_PORTS"), warp_scan_interval=max(300, _int("WARP_SCAN_INTERVAL", 1200)), warp_scan_sample=max(2, _int("WARP_SCAN_SAMPLE", 10)), warp_scan_concurrency=max(8, _int("WARP_SCAN_CONCURRENCY", 80)), warp_scan_timeout=max(.5, _int("WARP_SCAN_TIMEOUT_MS", 2500) / 1000), warp_scan_attempts=max(2, min(5, _int("WARP_SCAN_ATTEMPTS", 3))), warp_verify_top=max(4, _int("WARP_VERIFY_TOP", 24)), warp_pool_size=max(8, _int("WARP_POOL_SIZE", 100)), warp_per_config=max(1, _int("WARP_PER_CONFIG", 6)),
        store_tokens=_bool("STORE_TOKENS", True), request_timeout=max(5.0, float(_int("REQUEST_TIMEOUT", 30))), log_level=_str("LOG_LEVEL", "INFO").upper(),
    )

settings = load_settings()
