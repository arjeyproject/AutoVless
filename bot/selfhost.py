"""Self-hosted inbounds: VLESS-REALITY and Shadowsocks-2022 on your own box.

Why this module exists
----------------------
Everything else in this project rents its edge from Cloudflare, and that edge
comes with a rule attached: since 3 December 2024 the Self-Serve Subscription
Agreement forbids using the Services "to provide a virtual private network or
other similar proxy services" (2.2.1 j), and pinning traffic to hand-picked
Cloudflare addresses is separately forbidden by 2.2.1 b. Accounts that do it get
suspended, usually within days, and the configs die with the account. That is
not a bug in this bot and there is no patch for it: the platform is enforcing
its own terms.

So the fix is to stop depending on that edge. This module builds the two
inbounds that run on hardware you actually rent, terminate on your own IP, and
have no third-party account behind them to suspend:

  * VLESS with REALITY. No domain, no certificate, no CDN. The handshake it
    presents is a genuine TLS 1.3 handshake borrowed from a real, unrelated
    site, so there is no self-signed certificate to fingerprint and no SNI of
    yours on the wire. This is what the Xray-based panels use, and it is the
    single most durable shape available today.
  * Shadowsocks-2022 (``2022-blake3-aes-128-gcm``). The successor to the AEAD
    ciphers in ``bot/shadowsocks.py``: a session-based construction with
    BLAKE3-derived subkeys and replay protection built in, instead of the
    salt-per-connection AEAD scheme that predates it. It needs no plugin, no
    TLS wrapper and no WebSocket, which is why it can be handed out for free and
    fully automatically - there is nothing per-user to deploy.

Both are served by one ``sing-box`` process. ``scripts/install-selfhost.sh``
installs it and prints the environment block this module reads.

Nothing here talks to the database or to Cloudflare, so importing it can never
affect the existing panel flow.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid as uuid_lib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode

from .config import settings

# 16 bytes of key material: 2022-blake3-aes-128-gcm, the variant with the widest
# client support and hardware AES on every CPU worth renting.
SS2022_METHOD = "2022-blake3-aes-128-gcm"
SS2022_KEY_BYTES = 16
# REALITY is only worth running with Vision: it pads the first records so their
# sizes stop looking like a proxy handshake.
FLOW = "xtls-rprx-vision"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@dataclass(frozen=True)
class SelfHost:
    host: str
    reality_port: int
    reality_sni: str
    reality_pbk: str
    reality_sid: str
    reality_uuid: str
    ss_port: int
    ss_method: str
    ss_psk: str
    ss_per_user: bool

    @property
    def reality_ready(self) -> bool:
        return bool(self.host and self.reality_pbk and self.reality_uuid)

    @property
    def ss_ready(self) -> bool:
        return bool(self.host and self.ss_psk)

    @property
    def ready(self) -> bool:
        return self.reality_ready or self.ss_ready


def load() -> SelfHost:
    """Read the block ``install-selfhost.sh`` prints. All of it is optional."""
    return SelfHost(
        host=_env("SELFHOST_HOST"),
        reality_port=_int_env("REALITY_PORT", 443),
        reality_sni=_env("REALITY_SNI", "www.datadoghq.com"),
        reality_pbk=_env("REALITY_PBK"),
        reality_sid=_env("REALITY_SID"),
        reality_uuid=_env("REALITY_UUID"),
        ss_port=_int_env("SS2022_PORT", 8443),
        ss_method=_env("SS2022_METHOD", SS2022_METHOD),
        ss_psk=_env("SS2022_PSK"),
        # Off by default, and that is the whole point of the free tier: one
        # shared server key means a new user costs zero provisioning steps. Turn
        # it on only once ``scripts/selfhost-user.py`` is registering people, or
        # every derived credential will be refused by a server that never saw it.
        ss_per_user=_env("SELFHOST_PER_USER").lower() in {"1", "true", "yes", "on"},
    )


def enabled() -> bool:
    if _env("SELFHOST", "1").lower() in {"0", "false", "no", "off"}:
        return False
    return load().ready


# --------------------------------------------------------------------- #
# per-user secrets, derived rather than stored
# --------------------------------------------------------------------- #


def _digest(label: str) -> bytes:
    return hmac.new(
        settings.secret_key.encode("utf-8"), label.encode("utf-8"), hashlib.sha256
    ).digest()


def user_uuid(tg_id: int) -> str:
    """A stable per-user VLESS id.

    Derived, not random, so a restart or a rebuild hands the same person the
    same id and the config they saved last week still authenticates.
    """
    return str(uuid_lib.UUID(bytes=_digest(f"selfhost:vless:{int(tg_id)}")[:16], version=4))


def user_psk(tg_id: int) -> str:
    """The per-user half of a Shadowsocks-2022 key, base64, 16 bytes."""
    return _b64(_digest(f"selfhost:ss:{int(tg_id)}")[:SS2022_KEY_BYTES])


def ss_password(node: SelfHost, tg_id: Optional[int] = None) -> str:
    """What the client puts in its password field.

    Shadowsocks-2022 multi-user is ``<server psk>:<user psk>``; single-user is
    the server key on its own. Which one applies is not a style choice - it has
    to match how the inbound was written, so it follows ``SELFHOST_PER_USER``.
    """
    if node.ss_per_user and tg_id is not None:
        return f"{node.ss_psk}:{user_psk(tg_id)}"
    return node.ss_psk


def vless_uuid(node: SelfHost, tg_id: Optional[int] = None) -> str:
    if node.ss_per_user and tg_id is not None:
        return user_uuid(tg_id)
    return node.reality_uuid


# --------------------------------------------------------------------- #
# links
# --------------------------------------------------------------------- #


def _label(kind: str, brand: str = "") -> str:
    brand = brand or settings.brand
    return f"@{brand} | {kind} | \U0001f3e0 SELF-HOST | \U0001f30d GLOBAL"


def reality_link(node: SelfHost, tg_id: Optional[int] = None, brand: str = "") -> str:
    if not node.reality_ready:
        return ""
    params = {
        "encryption": "none",
        "security": "reality",
        "sni": node.reality_sni,
        "fp": "chrome",
        "pbk": node.reality_pbk,
        "type": "tcp",
        "flow": FLOW,
    }
    if node.reality_sid:
        params["sid"] = node.reality_sid
    query = urlencode(params, quote_via=quote, safe="")
    tag = quote(_label("\u26a1 VLESS-REALITY", brand), safe="")
    return f"vless://{vless_uuid(node, tg_id)}@{node.host}:{node.reality_port}?{query}#{tag}"


def ss_link(node: SelfHost, tg_id: Optional[int] = None, brand: str = "") -> str:
    """SIP002 ``ss://`` with the userinfo base64-encoded, as clients expect."""
    if not node.ss_ready:
        return ""
    userinfo = base64.urlsafe_b64encode(
        f"{node.ss_method}:{ss_password(node, tg_id)}".encode("utf-8")
    ).decode("ascii").rstrip("=")
    tag = quote(_label("\U0001f512 SS-2022", brand), safe="")
    return f"ss://{userinfo}@{node.host}:{node.ss_port}#{tag}"


def links(tg_id: Optional[int] = None, brand: str = "") -> list[str]:
    node = load()
    return [
        link
        for link in (reality_link(node, tg_id, brand), ss_link(node, tg_id, brand))
        if link
    ]


def subscription(tg_id: Optional[int] = None, brand: str = "") -> str:
    payload = "\n".join(links(tg_id, brand))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


# --------------------------------------------------------------------- #
# client exports
# --------------------------------------------------------------------- #


def singbox_outbounds(tg_id: Optional[int] = None, brand: str = "") -> list[dict]:
    node = load()
    out: list[dict] = []
    if node.reality_ready:
        item: dict = {
            "type": "vless",
            "tag": _label("\u26a1 VLESS-REALITY", brand),
            "server": node.host,
            "server_port": node.reality_port,
            "uuid": vless_uuid(node, tg_id),
            "flow": FLOW,
            "packet_encoding": "xudp",
            "tls": {
                "enabled": True,
                "server_name": node.reality_sni,
                "utls": {"enabled": True, "fingerprint": "chrome"},
                "reality": {"enabled": True, "public_key": node.reality_pbk},
            },
        }
        if node.reality_sid:
            item["tls"]["reality"]["short_id"] = node.reality_sid
        out.append(item)
    if node.ss_ready:
        out.append(
            {
                "type": "shadowsocks",
                "tag": _label("\U0001f512 SS-2022", brand),
                "server": node.host,
                "server_port": node.ss_port,
                "method": node.ss_method,
                "password": ss_password(node, tg_id),
            }
        )
    return out


def clash_proxies(tg_id: Optional[int] = None, brand: str = "") -> list[str]:
    node = load()
    blocks: list[str] = []
    if node.reality_ready:
        lines = [
            f'  - name: "{_label("VLESS-REALITY", brand)}"',
            "    type: vless",
            f"    server: {node.host}",
            f"    port: {node.reality_port}",
            f"    uuid: {vless_uuid(node, tg_id)}",
            "    network: tcp",
            "    udp: true",
            "    tls: true",
            f"    flow: {FLOW}",
            f"    servername: {node.reality_sni}",
            "    client-fingerprint: chrome",
            "    reality-opts:",
            f"      public-key: {node.reality_pbk}",
        ]
        if node.reality_sid:
            lines.append(f"      short-id: {node.reality_sid}")
        blocks.append("\n".join(lines))
    if node.ss_ready:
        blocks.append(
            "\n".join(
                [
                    f'  - name: "{_label("SS-2022", brand)}"',
                    "    type: ss",
                    f"    server: {node.host}",
                    f"    port: {node.ss_port}",
                    f"    cipher: {node.ss_method}",
                    f'    password: "{ss_password(node, tg_id)}"',
                    "    udp: true",
                ]
            )
        )
    return blocks


def status() -> dict:
    node = load()
    return {
        "enabled": enabled(),
        "host": node.host,
        "reality": node.reality_ready,
        "reality_port": node.reality_port,
        "sni": node.reality_sni,
        "shadowsocks": node.ss_ready,
        "ss_port": node.ss_port,
        "ss_method": node.ss_method,
        "per_user": node.ss_per_user,
    }


__all__ = [
    "FLOW",
    "SS2022_METHOD",
    "SelfHost",
    "clash_proxies",
    "enabled",
    "links",
    "load",
    "reality_link",
    "singbox_outbounds",
    "ss_link",
    "ss_password",
    "status",
    "subscription",
    "user_psk",
    "user_uuid",
    "vless_uuid",
]
