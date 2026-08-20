"""WARP identities and config generation.

What matters in Iran right now: plain WireGuard is identified by its fixed
handshake byte pattern and blackholed within moments of connecting. The fix is
obfuscation on the client side only, because the other end of a WARP tunnel is
Cloudflare's own plain WireGuard peer and cannot be changed.

So we emit AmneziaWG configs that stay byte compatible with a plain peer:

  * H1-H4 keep their WireGuard values and S1/S2 stay at zero, so every packet
    Cloudflare actually parses is untouched
  * the junk train (Jc / Jmin / Jmax) fires before the handshake, and those
    packets are simply discarded by the peer
  * I1 optionally prepends a QUIC-shaped decoy for AmneziaWG 1.5+ clients

That is what lets an obfuscated client talk to an unmodified WARP endpoint.
Parameters are derived per user and cached, so a rebuild keeps the same
fingerprint instead of looking like a brand new client every time.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import random
from typing import Optional, Sequence
from urllib.parse import quote

import httpx

from . import wireguard
from .config import settings

log = logging.getLogger("autovless.warp")

API_HOST = "https://api.cloudflareclient.com"
API_VERSIONS = ("v0a4005", "v0a2158")
HEADERS = {
    "CF-Client-Version": "a-6.30-3596",
    "User-Agent": "okhttp/3.12.1",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json",
}

# Used only when the scanner has nothing better yet.
FALLBACK_ENDPOINTS = (
    ("162.159.192.1", 2408),
    ("162.159.195.1", 500),
    ("188.114.96.1", 1701),
    ("188.114.98.1", 4500),
)


class WarpError(Exception):
    pass


# --------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------- #


def _tos_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _reserved(client_id: str) -> list[int]:
    if not client_id:
        return [0, 0, 0]
    try:
        raw = wireguard._raw(client_id)
    except Exception:  # noqa: BLE001
        return [0, 0, 0]
    return list(raw[:3]) if len(raw) >= 3 else [0, 0, 0]


async def _register_on(client: httpx.AsyncClient, version: str, public_key: str) -> dict:
    body = {
        "key": public_key,
        "install_id": "",
        "fcm_token": "",
        "tos": _tos_stamp(),
        "model": "PC",
        "serial_number": "",
        "locale": "en_US",
        "type": "Android",
    }
    response = await client.post(f"{API_HOST}/{version}/reg", json=body)
    if response.status_code >= 400:
        raise WarpError(f"registration refused ({response.status_code})")
    try:
        return response.json()
    except ValueError as exc:
        raise WarpError("unreadable registration response") from exc


async def _enable_warp(client: httpx.AsyncClient, version: str, data: dict) -> None:
    """A fresh device has WARP switched off; without this the tunnel carries nothing."""
    device_id = data.get("id")
    token = data.get("token")
    if not device_id or not token:
        return
    try:
        await client.patch(
            f"{API_HOST}/{version}/reg/{device_id}",
            json={"warp_enabled": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as error:
        log.warning("could not enable warp on device: %s", error)


def _identity_from(data: dict, private_key: str, version: str) -> dict:
    try:
        config = data["config"]
        peer = config["peers"][0]
        addresses = config["interface"]["addresses"]
    except (KeyError, IndexError, TypeError) as exc:
        raise WarpError("unexpected warp payload") from exc

    client_id = config.get("client_id") or ""
    account = data.get("account") or {}
    return {
        "private_key": private_key,
        "peer_public_key": peer["public_key"],
        "client_id": client_id,
        "reserved": _reserved(client_id),
        "v4": addresses["v4"],
        "v6": addresses["v6"],
        "device_id": data.get("id", ""),
        "token": data.get("token", ""),
        "account_type": account.get("account_type", "free"),
        "quota": account.get("quota"),
        "license": account.get("license", ""),
        "api": version,
    }


async def provision(timeout: Optional[float] = None) -> dict:
    """Register a brand new WARP device and return everything a config needs."""
    private_key, public_key = wireguard.keypair()
    timeout = timeout or settings.request_timeout
    last: Optional[Exception] = None

    async with httpx.AsyncClient(timeout=timeout, headers=HEADERS) as client:
        for version in API_VERSIONS:
            try:
                data = await _register_on(client, version, public_key)
            except (WarpError, httpx.HTTPError) as error:
                last = error
                log.info("warp registration on %s failed: %s", version, error)
                continue
            await _enable_warp(client, version, data)
            identity = _identity_from(data, private_key, version)
            if settings.warp_license:
                identity = await _apply(client, identity, settings.warp_license)
            return identity

    raise WarpError(str(last) if last else "registration failed")


async def _apply(client: httpx.AsyncClient, identity: dict, license_key: str) -> dict:
    device_id = identity.get("device_id")
    token = identity.get("token")
    if not device_id or not token:
        raise WarpError("this identity cannot take a license")

    version = identity.get("api") or API_VERSIONS[0]
    auth = {"Authorization": f"Bearer {token}"}
    response = await client.put(
        f"{API_HOST}/{version}/reg/{device_id}/account",
        json={"license": license_key.strip()},
        headers=auth,
    )
    if response.status_code >= 400:
        raise WarpError(f"license refused ({response.status_code})")

    account = {}
    try:
        account = response.json() or {}
    except ValueError:
        pass

    # Re-read the device so a rotated peer key is not missed.
    try:
        fresh = await client.get(f"{API_HOST}/{version}/reg/{device_id}", headers=auth)
        if fresh.status_code < 400:
            payload = fresh.json()
            config = payload.get("config") or {}
            peers = config.get("peers") or []
            if peers:
                identity["peer_public_key"] = peers[0].get(
                    "public_key", identity["peer_public_key"]
                )
            client_id = config.get("client_id")
            if client_id:
                identity["client_id"] = client_id
                identity["reserved"] = _reserved(client_id)
            account = payload.get("account") or account
    except (httpx.HTTPError, ValueError):
        pass

    identity["account_type"] = account.get("account_type", "warp_plus")
    identity["quota"] = account.get("quota")
    identity["license"] = license_key.strip()
    return identity


async def apply_license(identity: dict, license_key: str) -> dict:
    """Turn a free identity into WARP+ using a license key."""
    async with httpx.AsyncClient(timeout=settings.request_timeout, headers=HEADERS) as client:
        return await _apply(client, dict(identity), license_key)


# --------------------------------------------------------------------- #
# obfuscation profile
# --------------------------------------------------------------------- #


def _quic_signature(rng: random.Random) -> str:
    """A CPS blob shaped like a QUIC Initial packet, for AmneziaWG 1.5+ clients."""
    dcid = "".join(rng.choice("0123456789abcdef") for _ in range(16))
    header = "c300000001" + "08" + dcid + "00" + "00"
    return f"<b 0x{header}><r 4><t><r 900>"


def obfuscation(seed: object) -> dict:
    """Per-user junk train. Stable for a given seed, different between users.

    Only pre-handshake junk is used. Header magic and packet prefixes stay at
    WireGuard defaults because the peer on the other side is Cloudflare's and
    would drop anything it cannot parse.
    """
    rng = random.Random(f"{settings.secret_key}:{seed}")
    jmin = rng.randint(80, 220)
    jmax = rng.randint(jmin + 320, 1024)
    return {
        "jc": rng.randint(4, 8),
        "jmin": jmin,
        "jmax": jmax,
        "i1": _quic_signature(rng),
    }


def _addresses(identity: dict) -> list[str]:
    out = []
    if identity.get("v4"):
        out.append(f"{identity['v4']}/32")
    if identity.get("v6"):
        out.append(f"{identity['v6']}/128")
    return out


def _endpoint(endpoints: Sequence[dict], index: int = 0) -> tuple[str, int]:
    if endpoints:
        chosen = endpoints[min(index, len(endpoints) - 1)]
        return str(chosen["ip"]), int(chosen["port"])
    return FALLBACK_ENDPOINTS[index % len(FALLBACK_ENDPOINTS)]


def endpoint_label(endpoints: Sequence[dict], index: int = 0) -> str:
    host, port = _endpoint(endpoints, index)
    return f"{host}:{port}"


# --------------------------------------------------------------------- #
# config formats
# --------------------------------------------------------------------- #


def wireguard_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    mtu: Optional[int] = None,
    dns: Optional[str] = None,
) -> str:
    """Plain WireGuard. Kept for clients without obfuscation support."""
    host, port = _endpoint(endpoints)
    return "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {identity['private_key']}",
            f"Address = {', '.join(_addresses(identity))}",
            f"DNS = {dns or settings.warp_dns}",
            f"MTU = {mtu or settings.warp_mtu}",
            "",
            "[Peer]",
            f"PublicKey = {identity['peer_public_key']}",
            "AllowedIPs = 0.0.0.0/0, ::/0",
            f"Endpoint = {host}:{port}",
            "PersistentKeepalive = 25",
            "",
        ]
    )


def amnezia_conf(
    identity: dict,
    endpoints: Sequence[dict] = (),
    profile: Optional[dict] = None,
    mtu: Optional[int] = None,
    dns: Optional[str] = None,
    signature: bool = False,
) -> str:
    """AmneziaWG. ``signature`` adds the I1 decoy, which needs AmneziaWG 1.5+."""
    host, port = _endpoint(endpoints)
    profile = profile or obfuscation(identity.get("private_key", ""))

    lines = [
        "[Interface]",
        f"PrivateKey = {identity['private_key']}",
        f"Address = {', '.join(_addresses(identity))}",
        f"DNS = {dns or settings.warp_dns}",
        f"MTU = {mtu or settings.warp_mtu}",
        f"Jc = {profile['jc']}",
        f"Jmin = {profile['jmin']}",
        f"Jmax = {profile['jmax']}",
        # Left at WireGuard defaults on purpose: Cloudflare's peer is unmodified.
        "S1 = 0",
        "S2 = 0",
        "H1 = 1",
        "H2 = 2",
        "H3 = 3",
        "H4 = 4",
    ]
    if signature:
        lines.append(f"I1 = {profile['i1']}")
    lines += [
        "",
        "[Peer]",
        f"PublicKey = {identity['peer_public_key']}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        f"Endpoint = {host}:{port}",
        "PersistentKeepalive = 25",
        "",
    ]
    return "\n".join(lines)


def warp_link(
    identity: dict,
    endpoints: Sequence[dict] = (),
    index: int = 0,
    name: Optional[str] = None,
    mtu: Optional[int] = None,
) -> str:
    """wireguard:// share link for Xray based clients, with UDP noise attached."""
    host, port = _endpoint(endpoints, index)
    label = name or f"{settings.brand}-WARP"
    reserved = "%2C".join(str(part) for part in identity.get("reserved") or [0, 0, 0])
    address = "%2C".join(quote(item, safe="") for item in _addresses(identity))
    return (
        f"wireguard://{quote(identity['private_key'], safe='')}@{host}:{port}"
        f"?address={address}"
        f"&publickey={quote(identity['peer_public_key'], safe='')}"
        f"&reserved={reserved}"
        f"&mtu={mtu or settings.warp_mtu}"
        "&wnoise=quic&wnoisecount=15&wpayloadsize=1-1500&wnoisedelay=1-10"
        f"#{quote(label, safe='')}"
    )


def links(identity: dict, endpoints: Sequence[dict]) -> list[str]:
    total = max(1, len(endpoints)) if endpoints else len(FALLBACK_ENDPOINTS)
    return [
        warp_link(identity, endpoints, index, f"{settings.brand}-WARP-{index + 1}")
        for index in range(total)
    ]


def singbox_json(identity: dict, endpoints: Sequence[dict], mtu: Optional[int] = None) -> str:
    outbounds = []
    total = max(1, len(endpoints)) if endpoints else len(FALLBACK_ENDPOINTS)
    for index in range(total):
        host, port = _endpoint(endpoints, index)
        outbounds.append(
            {
                "type": "wireguard",
                "tag": f"{settings.brand}-WARP-{index + 1}",
                "server": host,
                "server_port": port,
                "local_address": _addresses(identity),
                "private_key": identity["private_key"],
                "peer_public_key": identity["peer_public_key"],
                "reserved": identity.get("reserved") or [0, 0, 0],
                "mtu": mtu or settings.warp_mtu,
            }
        )
    return json.dumps({"outbounds": outbounds}, indent=2, ensure_ascii=False)


def clash_yaml(identity: dict, endpoints: Sequence[dict], mtu: Optional[int] = None) -> str:
    total = max(1, len(endpoints)) if endpoints else len(FALLBACK_ENDPOINTS)
    reserved = ", ".join(str(part) for part in identity.get("reserved") or [0, 0, 0])
    proxies: list[str] = []
    names: list[str] = []

    for index in range(total):
        host, port = _endpoint(endpoints, index)
        name = f"{settings.brand}-WARP-{index + 1}"
        names.append(f'      - "{name}"')
        block = [
            f'  - name: "{name}"',
            "    type: wireguard",
            f"    server: {host}",
            f"    port: {port}",
            f"    ip: {identity['v4']}",
        ]
        if identity.get("v6"):
            block.append(f"    ipv6: {identity['v6']}")
        block += [
            f"    private-key: {identity['private_key']}",
            f"    public-key: {identity['peer_public_key']}",
            f"    reserved: [{reserved}]",
            f"    mtu: {mtu or settings.warp_mtu}",
            "    udp: true",
            "    remote-dns-resolve: true",
        ]
        proxies.append("\n".join(block))

    return "\n".join(
        [
            f"# {settings.brand} WARP",
            "mixed-port: 7890",
            "mode: rule",
            "proxies:",
            "\n".join(proxies),
            "proxy-groups:",
            f'  - name: "{settings.brand}-WARP"',
            "    type: url-test",
            "    url: http://cp.cloudflare.com/generate_204",
            "    interval: 300",
            "    proxies:",
            "\n".join(names),
            "rules:",
            f"  - MATCH,{settings.brand}-WARP",
            "",
        ]
    )
