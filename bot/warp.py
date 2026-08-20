"""WireGuard / WARP key provisioning against the Cloudflare consumer API."""

from __future__ import annotations

import base64
import datetime as dt
from typing import Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

API = "https://api.cloudflareclient.com/v0a2158"
HEADERS = {
    "CF-Client-Version": "a-6.30-3596",
    "User-Agent": "okhttp/3.12.1",
    "Content-Type": "application/json; charset=UTF-8",
}
ENDPOINTS = (
    "engage.cloudflareclient.com:2408",
    "162.159.192.1:2408",
    "162.159.195.1:2408",
    "[2606:4700:d0::a29f:c001]:2408",
)


class WarpError(Exception):
    pass


def _keypair() -> tuple[str, str]:
    private = X25519PrivateKey.generate()
    priv = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(priv).decode("ascii"), base64.b64encode(pub).decode("ascii")


def _reserved(client_id: str) -> list[int]:
    raw = base64.b64decode(client_id + "=" * (-len(client_id) % 4))
    return list(raw[:3])


async def provision(timeout: float = 25.0) -> dict:
    """Register a fresh WARP identity and return everything needed for a config."""
    private_key, public_key = _keypair()
    body = {
        "key": public_key,
        "install_id": "",
        "fcm_token": "",
        "tos": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "+00:00"),
        "model": "PC",
        "serial_number": "",
        "locale": "en_US",
        "type": "Android",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=HEADERS) as client:
        try:
            response = await client.post(f"{API}/reg", json=body)
        except httpx.HTTPError as exc:
            raise WarpError(f"network error: {exc}") from exc

    if response.status_code >= 400:
        raise WarpError(f"warp registration failed ({response.status_code})")

    try:
        data = response.json()
        config = data["config"]
        peer = config["peers"][0]
        addresses = config["interface"]["addresses"]
    except (ValueError, KeyError, IndexError) as exc:
        raise WarpError("unexpected warp response") from exc

    return {
        "private_key": private_key,
        "public_key": peer["public_key"],
        "client_id": config.get("client_id", ""),
        "reserved": _reserved(config["client_id"]) if config.get("client_id") else [0, 0, 0],
        "v4": addresses["v4"],
        "v6": addresses["v6"],
        "endpoint": ENDPOINTS[0],
        "account_type": (data.get("account") or {}).get("account_type", "free"),
    }


def wireguard_conf(identity: dict, mtu: int = 1280, dns: str = "1.1.1.1, 1.0.0.1") -> str:
    return "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {identity['private_key']}",
            f"Address = {identity['v4']}/32",
            f"Address = {identity['v6']}/128",
            f"DNS = {dns}",
            f"MTU = {mtu}",
            "",
            "[Peer]",
            f"PublicKey = {identity['public_key']}",
            "AllowedIPs = 0.0.0.0/0",
            "AllowedIPs = ::/0",
            f"Endpoint = {identity['endpoint']}",
            "PersistentKeepalive = 25",
            "",
        ]
    )


def warp_link(identity: dict, name: str = "AutoVless-WARP") -> str:
    reserved = "%2C".join(str(x) for x in identity["reserved"])
    host, _, port = identity["endpoint"].rpartition(":")
    return (
        f"wireguard://{identity['private_key']}@{host}:{port}"
        f"?address={identity['v4']}%2F32&reserved={reserved}"
        f"&publickey={identity['public_key']}&mtu=1280#{name}"
    )
