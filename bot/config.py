"""Runtime configuration, loaded once from the environment."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Cloudflare edge ports that speak TLS. Everything else is treated as plain HTTP.
TLS_PORTS: tuple[int, ...] = (443, 2053, 2083, 2087, 2096, 8443)
HTTP_PORTS: tuple[int, ...] = (80, 8080, 8880, 2052, 2082, 2086, 2095)

# Public lists of Cloudflare edges that are known to behave well from Iran.
DEFAULT_CLEAN_SOURCES: tuple[str, ...] = (
    "https://ipdb.030101.xyz/api/bestcf.txt",
)

# Hostnames whose DNS answer is kept pointed at healthy Cloudflare edges by the
# community. They rotate on their own, so a config that carries the hostname
# keeps working after the address behind it changes. One of these is mounted on
# every panel as a self-healing entry point.
DEFAULT_CLEAN_DOMAINS: tuple[str, ...] = (
    "cf.090227.xyz",
    "cdn.xn--b6gac.eu.org",
    "cf.877774.xyz",
    "cfip.cfcdn.eu.org",
)

# Public lists of relays that forward TCP to the Cloudflare edge.
DEFAULT_PROXY_SOURCES: tuple[str, ...] = (
    "https://ipdb.030101.xyz/api/bestproxy.txt",
)

# Long lived community relays, used as a floor under the scanner.
DEFAULT_PROXY_SEEDS: tuple[str, ...] = (
    "proxyip.fxxk.dedyn.io",
    "proxyip.aliyun.fxxk.dedyn.io",
    "proxyip.oracle.fxxk.dedyn.io",
    "proxyip.digitalocean.fxxk.dedyn.io",
    "cdn.xn--b6gac.eu.org",
    "cdn-all.xn--b6gac.eu.org",
    "bpb.yousef.isegaro.com",
    "edgetunnel.anycast.eu.org",
)


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    raw = _str(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = _str(name)
    if not raw:
        return default
    parts = [chunk.strip() for chunk in raw.replace(";", ",").replace("\n", ",").split(",")]
    return tuple(dict.fromkeys(part for part in parts if part))


def _ids(name: str) -> tuple[int, ...]:
    out: list[int] = []
    for chunk in _str(name).replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            out.append(int(chunk))
    return tuple(dict.fromkeys(out))


def _int_list(name: str, default: tuple[int, ...] = ()) -> tuple[int, ...]:
    raw = _str(name)
    if not raw:
        return default
    out = [int(chunk) for chunk in raw.replace(";", ",").split(",") if chunk.strip().isdigit()]
    return tuple(dict.fromkeys(out)) or default


def _ports(name: str, default: tuple[int, ...], allowed: tuple[int, ...]) -> tuple[int, ...]:
    raw = _str(name)
    if not raw:
        return default
    out = [int(c) for c in raw.replace(";", ",").split(",") if c.strip().isdigit()]
    out = [p for p in out if p in allowed]
    return tuple(out) or default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    secret_key: str

    data_dir: Path
    db_path: Path
    worker_file: Path

    brand: str
    support_url: str
    channel_url: str
    donate_url: str
    github_url: str
    webapp_url: str
    default_lang: str

    tls_ports: tuple[int, ...]
    http_ports: tuple[int, ...]
    tls_config_count: int
    http_config_count: int

    # ------------------------------------------------------------- scanner
    scan_interval: int
    scan_batch: int
    scan_concurrency: int
    scan_timeout: float
    verify_top: int
    verify_probes: int
    scan_waves: int
    scan_min_verified: int
    pool_size: int
    clean_ip_sources: tuple[str, ...]
    clean_domains: tuple[str, ...]
    max_fails: int

    # --------------------------------------------------------------- relays
    proxy_ip: str
    proxy_seeds: tuple[str, ...]
    proxy_sources: tuple[str, ...]
    proxy_ports: tuple[int, ...]
    proxy_scan_interval: int
    proxy_scan_limit: int
    proxy_pool_size: int
    proxy_per_panel: int

    # --------------------------------------------------------------- worker
    dns_server: str
    fallback_host: str
    health_attempts: int
    sub_sources: tuple[str, ...]
    sub_refresh: int

    # ------------------------------------------------------------ autopilot
    autopilot: bool
    autopilot_interval: int
    autopilot_batch: int
    autopilot_max_age: int

    # ---------------------------------------------------------------- warp
    warp_enabled: bool
    warp_amnezia: bool
    warp_mtu: int
    warp_dns: str
    warp_license: str
    warp_ports: tuple[int, ...]
    warp_scan_interval: int
    warp_scan_sample: int
    warp_scan_concurrency: int
    warp_scan_timeout: float
    warp_scan_attempts: int
    warp_verify_top: int
    warp_pool_size: int
    warp_per_config: int

    store_tokens: bool
    request_timeout: float
    log_level: str
    compatibility_date: str = "2024-11-01"
    languages: tuple[str, ...] = field(default=("fa", "en"))

    @property
    def config_count(self) -> int:
        return self.tls_config_count + self.http_config_count

    @property
    def all_ports(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys(self.tls_ports + self.http_ports))

    def is_admin(self, tg_id: int) -> bool:
        return tg_id in self.admin_ids


def load_settings() -> Settings:
    data_dir = Path(_str("DATA_DIR", str(BASE_DIR / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)

    secret = _str("SECRET_KEY")
    if not secret:
        keyfile = data_dir / ".secret"
        if keyfile.exists():
            secret = keyfile.read_text(encoding="utf-8").strip()
        else:
            secret = secrets.token_urlsafe(48)
            keyfile.write_text(secret, encoding="utf-8")
            keyfile.chmod(0o600)

    lang = _str("DEFAULT_LANG", "fa").lower()
    if lang not in {"fa", "en"}:
        lang = "fa"

    proxy_ip = _str("PROXY_IP")
    proxy_seeds = _list("PROXY_IP", DEFAULT_PROXY_SEEDS)
    clean_sources = _list("CLEAN_IP_SOURCES", DEFAULT_CLEAN_SOURCES)

    return Settings(
        bot_token=_str("BOT_TOKEN"),
        admin_ids=_ids("ADMIN_IDS"),
        secret_key=secret,
        data_dir=data_dir,
        db_path=Path(_str("DB_PATH", str(data_dir / "autovless.db"))),
        worker_file=Path(_str("WORKER_FILE", str(BASE_DIR / "worker" / "vless-worker.js"))),
        brand=_str("BRAND", "AutoVless"),
        support_url=_str("SUPPORT_URL", "https://t.me/AutoVless"),
        channel_url=_str("CHANNEL_URL", "https://t.me/AutoVless"),
        donate_url=_str("DONATE_URL"),
        github_url=_str("GITHUB_URL", "https://github.com/arjeyproject/AutoVless"),
        webapp_url=_str("WEBAPP_URL"),
        default_lang=lang,
        tls_ports=_ports("TLS_PORTS", (443,), TLS_PORTS),
        http_ports=_ports("HTTP_PORTS", (80,), HTTP_PORTS),
        tls_config_count=max(0, _int("TLS_CONFIG_COUNT", 4)),
        http_config_count=max(0, _int("HTTP_CONFIG_COUNT", 2)),
        scan_interval=max(60, _int("SCAN_INTERVAL", 600)),
        scan_batch=max(64, _int("SCAN_BATCH", 900)),
        scan_concurrency=max(16, _int("SCAN_CONCURRENCY", 160)),
        scan_timeout=max(0.3, float(_int("SCAN_TIMEOUT_MS", 1200)) / 1000.0),
        verify_top=max(6, _int("VERIFY_TOP", 28)),
        verify_probes=max(1, min(4, _int("VERIFY_PROBES", 2))),
        scan_waves=max(1, min(5, _int("SCAN_WAVES", 3))),
        scan_min_verified=max(2, _int("SCAN_MIN_VERIFIED", 8)),
        pool_size=max(12, _int("POOL_SIZE", 120)),
        clean_ip_sources=clean_sources,
        clean_domains=_list("CLEAN_DOMAINS", DEFAULT_CLEAN_DOMAINS),
        max_fails=max(1, _int("MAX_FAILS", 3)),
        proxy_ip=proxy_ip,
        proxy_seeds=proxy_seeds,
        proxy_sources=_list("PROXY_IP_SOURCES", DEFAULT_PROXY_SOURCES),
        proxy_ports=_ports("PROXY_PORTS", (443,), TLS_PORTS),
        proxy_scan_interval=max(300, _int("PROXY_SCAN_INTERVAL", 1800)),
        proxy_scan_limit=max(16, _int("PROXY_SCAN_LIMIT", 240)),
        proxy_pool_size=max(4, _int("PROXY_POOL_SIZE", 40)),
        proxy_per_panel=max(1, _int("PROXY_PER_PANEL", 4)),
        dns_server=_str("DNS_SERVER", "8.8.8.8"),
        fallback_host=_str("FALLBACK_HOST", "www.wikipedia.org"),
        health_attempts=max(2, _int("HEALTH_ATTEMPTS", 6)),
        sub_sources=_list("SUB_SOURCES", clean_sources),
        sub_refresh=max(60, _int("SUB_REFRESH", 300)),
        autopilot=_bool("AUTOPILOT", True),
        autopilot_interval=max(120, _int("AUTOPILOT_INTERVAL", 900)),
        autopilot_batch=max(1, _int("AUTOPILOT_BATCH", 6)),
        autopilot_max_age=max(600, _int("AUTOPILOT_MAX_AGE", 21600)),
        warp_enabled=_bool("WARP_ENABLED", True),
        warp_amnezia=_bool("WARP_AMNEZIA", True),
        warp_mtu=max(1000, min(1420, _int("WARP_MTU", 1280))),
        warp_dns=_str("WARP_DNS", "1.1.1.1, 1.0.0.1"),
        warp_license=_str("WARP_LICENSE"),
        warp_ports=_int_list("WARP_PORTS"),
        warp_scan_interval=max(300, _int("WARP_SCAN_INTERVAL", 1800)),
        warp_scan_sample=max(2, _int("WARP_SCAN_SAMPLE", 6)),
        warp_scan_concurrency=max(8, _int("WARP_SCAN_CONCURRENCY", 64)),
        warp_scan_timeout=max(0.5, float(_int("WARP_SCAN_TIMEOUT_MS", 2500)) / 1000.0),
        warp_scan_attempts=max(1, min(4, _int("WARP_SCAN_ATTEMPTS", 2))),
        warp_verify_top=max(4, _int("WARP_VERIFY_TOP", 16)),
        warp_pool_size=max(8, _int("WARP_POOL_SIZE", 60)),
        warp_per_config=max(1, _int("WARP_PER_CONFIG", 4)),
        store_tokens=_bool("STORE_TOKENS", True),
        request_timeout=max(5.0, float(_int("REQUEST_TIMEOUT", 30))),
        log_level=_str("LOG_LEVEL", "INFO").upper(),
    )


settings = load_settings()
