"""Shadowsocks AEAD over WebSocket: the third wire signature.

Why a third protocol at all
---------------------------
VLESS and Trojan already share one endpoint, and that pairing works because the
two handshakes look nothing alike to a DPI box. Shadowsocks adds a third shape
that is unlike either: there is no version byte, no hex preamble and no
plaintext structure anywhere - the very first byte on the wire is one of 32
random salt bytes, and everything after it is AEAD ciphertext. A classifier
tuned to spot a VLESS header or a Trojan digest has nothing to match on.

Why it is routed by path instead of sniffed
------------------------------------------
The worker tells VLESS from Trojan by looking at the first frame. That trick
cannot extend to Shadowsocks, precisely because of what makes it useful: random
bytes are indistinguishable from a VLESS header by inspection, and guessing
wrong means a silent auth failure that looks exactly like a dead endpoint. So
Shadowsocks gets its own WebSocket path (``SS_PATH``, ``/ss`` by default) and the
worker dispatches on that. Same address, same port, same worker.

Why the key is computed here and bound to the worker
---------------------------------------------------
Every Shadowsocks client turns the password into a master key with
``EVP_BytesToKey``, which is an MD5 chain. Workers' WebCrypto has SHA-1 through
SHA-512 and no MD5 at all, so the worker cannot do that derivation. It does not
have to: the bot derives the key here, binds it as ``SS_KEY`` hex, and the worker
goes straight to HKDF-SHA1 for the per-connection subkey, which WebCrypto does
support. The password in the link and the key in the binding are two views of the
same secret, and ``bot.shadowsocks`` is the only place that knows both.

The cipher is ``aes-256-gcm``: hardware accelerated everywhere, and the default
every client already agrees on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Sequence
from urllib.parse import quote, urlencode

from .config import settings
from .vless import is_tls

METHOD = "aes-256-gcm"
KEY_BYTES = 32
SALT_BYTES = 32
# The plugin every client uses to put Shadowsocks inside a WebSocket. The path is
# what the worker dispatches on, so it is not cosmetic.
PLUGIN = "v2ray-plugin"


def enabled() -> bool:
    """Whether Shadowsocks links are offered.

    Off by default, and that is deliberate rather than shy: the links are only
    useful once the worker bundle in front of them carries the inbound, so the
    operator turns this on in the same step as the worker that answers it.
    """
    return (os.getenv("SS") or "").strip().lower() in {"1", "true", "yes", "on"}


def path() -> str:
    """The WebSocket path Shadowsocks lives on. Always leading-slashed."""
    raw = (os.getenv("SS_PATH") or "/ss").strip()
    return raw if raw.startswith("/") else f"/{raw}"


def password_for(uuid: str) -> str:
    """A per-panel password derived from the account uuid.

    Deterministic, so a rebuild that keeps the uuid keeps the password and every
    config a user already saved carries on working. It is not the uuid itself: a
    password that is also the VLESS identity would mean one leaked config
    exposes both inbounds.
    """
    digest = hmac.new(
        settings.secret_key.encode("utf-8"), f"ss:{uuid}".encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode("ascii").rstrip("=")


def master_key(password: str, length: int = KEY_BYTES) -> bytes:
    """``EVP_BytesToKey`` with MD5, which is what every Shadowsocks client does.

    For a 32 byte key this is two MD5 rounds chained. Verified byte for byte
    against the key a stock client derives from the same password.
    """
    out = b""
    block = b""
    secret = password.encode("utf-8")
    while len(out) < length:
        block = hashlib.md5(block + secret).digest()
        out += block
    return out[:length]


def key_hex(uuid: str) -> str:
    """The ``SS_KEY`` binding: the master key the worker needs, as hex."""
    return master_key(password_for(uuid)).hex()


def usable(endpoints: Sequence[dict]) -> list[dict]:
    """TLS endpoints only.

    The same reasoning as Trojan: the WebSocket carries the whole Shadowsocks
    stream, and on a plain port that stream crosses the network without a TLS
    record around it. The cipher still protects the payload, but the point of
    hiding inside ordinary HTTPS is gone, and most clients refuse the plugin
    without ``tls`` anyway.
    """
    return [row for row in endpoints if is_tls(int(row["port"]))]


def _plugin_opts(host: str) -> str:
    """SIP003 plugin options. Semicolons, in the order clients expect."""
    return ";".join(
        [
            PLUGIN,
            "mode=websocket",
            "tls",
            f"host={host}",
            f"path={path()}",
            "mux=0",
        ]
    )


def _remark(endpoint: dict, index: int, brand: str = "") -> str:
    brand = brand or settings.brand
    badge = "\U0001f6e1" if endpoint.get("kind") != "domain" else "\U0001f300"
    ping = f"{round(float(endpoint.get('latency') or 0))}ms" if endpoint.get("latency") else "auto"
    return (
        f"@{brand} | {badge} SS | \U0001f30d GLOBAL | {ping} | "
        f"{endpoint.get('colo') or 'CF'} | #{index}"
    )


def build_link(uuid: str, host: str, endpoint: dict, index: int, brand: str = "") -> str:
    """A SIP002 ``ss://`` link with the websocket plugin attached."""
    userinfo = base64.urlsafe_b64encode(
        f"{METHOD}:{password_for(uuid)}".encode("utf-8")
    ).decode("ascii").rstrip("=")
    query = urlencode({"plugin": _plugin_opts(host)})
    label = quote(_remark(endpoint, index, brand), safe="")
    return f"ss://{userinfo}@{endpoint['ip']}:{endpoint['port']}?{query}#{label}"


def build_links(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> list[str]:
    return [
        build_link(uuid, host, endpoint, index, brand)
        for index, endpoint in enumerate(usable(endpoints), start=1)
    ]


def clash_proxies(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> list[str]:
    """Clash/Mihomo blocks. Returned as text so the caller can splice them in."""
    blocks: list[str] = []
    for index, endpoint in enumerate(usable(endpoints), start=1):
        name = _remark(endpoint, index, brand).replace('"', "'")
        blocks.append(
            "\n".join(
                [
                    f'  - name: "{name}"',
                    "    type: ss",
                    f"    server: {endpoint['ip']}",
                    f"    port: {endpoint['port']}",
                    f"    cipher: {METHOD}",
                    f"    password: {password_for(uuid)}",
                    "    udp: true",
                    f"    plugin: {PLUGIN}",
                    "    plugin-opts:",
                    "      mode: websocket",
                    "      tls: true",
                    f"      host: {host}",
                    f'      path: "{path()}"',
                    "      mux: false",
                ]
            )
        )
    return blocks


def names(uuid: str, host: str, endpoints: Sequence[dict], brand: str = "") -> list[str]:
    return [
        _remark(endpoint, index, brand).replace('"', "'")
        for index, endpoint in enumerate(usable(endpoints), start=1)
    ]


def singbox_outbounds(
    uuid: str, host: str, endpoints: Sequence[dict], brand: str = ""
) -> list[dict]:
    """sing-box reaches this inbound through the v2ray plugin as well."""
    out: list[dict] = []
    for index, endpoint in enumerate(usable(endpoints), start=1):
        out.append(
            {
                "type": "shadowsocks",
                "tag": _remark(endpoint, index, brand),
                "server": str(endpoint["ip"]),
                "server_port": int(endpoint["port"]),
                "method": METHOD,
                "password": password_for(uuid),
                "plugin": PLUGIN,
                "plugin_opts": f"mode=websocket;tls;host={host};path={path()};mux=0",
            }
        )
    return out


def bindings(uuid: str) -> dict[str, str]:
    """What the worker needs to serve this inbound."""
    return {
        "SS": "true" if enabled() else "false",
        "SS_KEY": key_hex(uuid),
        "SS_METHOD": METHOD,
        "SS_PATH": path(),
    }


__all__ = [
    "METHOD",
    "PLUGIN",
    "bindings",
    "enabled",
    "build_link",
    "build_links",
    "clash_proxies",
    "key_hex",
    "master_key",
    "names",
    "password_for",
    "path",
    "singbox_outbounds",
    "usable",
]
