"""A hand-rolled WireGuard handshake, used to prove an endpoint is really alive.

WARP endpoints are deliberately silent: they answer nothing except a valid
Noise_IK handshake initiation. There is no TCP socket to connect to and ICMP
says nothing about a UDP port, so a completed handshake is the only honest
reachability test. We build a genuine 148 byte initiation with real keys and
wait for the 92 byte type-2 response.

Nothing here brings up a tunnel. The reply on its own is the answer we need.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import secrets
import socket
import struct
import time
from typing import Optional, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

CONSTRUCTION = b"Noise_IKpsk2_25519_ChaChaPoly_BLAKE2s"
IDENTIFIER = b"WireGuard v1 zx2c4 Jason@zx2c4.com"
LABEL_MAC1 = b"mac1----"

MSG_INITIATION = 1
MSG_RESPONSE = 2
INITIATION_SIZE = 148
TAI64N_BASE = 0x400000000000000A


# --------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------- #


def _hash(*parts: bytes) -> bytes:
    digest = hashlib.blake2s(digest_size=32)
    for part in parts:
        digest.update(part)
    return digest.digest()


def _mac(key: bytes, data: bytes) -> bytes:
    return hashlib.blake2s(data, digest_size=16, key=key).digest()


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.blake2s).digest()


def _kdf(key: bytes, data: bytes, count: int) -> list[bytes]:
    """HKDF expand over HMAC-BLAKE2s, exactly as the WireGuard paper defines it."""
    tau = _hmac(key, data)
    out: list[bytes] = []
    previous = b""
    for index in range(1, count + 1):
        previous = _hmac(tau, previous + bytes([index]))
        out.append(previous)
    return out


def _seal(key: bytes, counter: int, plaintext: bytes, associated: bytes) -> bytes:
    nonce = b"\x00" * 4 + struct.pack("<Q", counter)
    return ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated)


def _tai64n(moment: Optional[float] = None) -> bytes:
    moment = time.time() if moment is None else moment
    seconds = int(moment)
    nanos = int((moment - seconds) * 1_000_000_000)
    return struct.pack(">QI", TAI64N_BASE + seconds, nanos)


def decode_key(value: str) -> bytes:
    """Raw bytes behind a base64 key or client id, padding tolerant."""
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded)


# Kept as a private alias: several call sites reached for it before it had a
# public name.
_raw = decode_key


def public_of(private_key: str) -> str:
    """The public half of a base64 X25519 private key."""
    private = X25519PrivateKey.from_private_bytes(decode_key(private_key))
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def keypair() -> tuple[str, str]:
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


# --------------------------------------------------------------------- #
# handshake initiation
# --------------------------------------------------------------------- #


def build_initiation(
    private_key: str,
    peer_public_key: str,
    reserved: Sequence[int] = (0, 0, 0),
) -> tuple[bytes, int]:
    """Return (packet, sender_index) for a fresh handshake initiation.

    ``reserved`` carries the WARP client id. Cloudflare uses those three bytes
    to route the session to the right account, so we send the real ones instead
    of zeros: that makes the probe a genuine end to end test.
    """
    static_private_raw = decode_key(private_key)
    peer_public_raw = decode_key(peer_public_key)

    static_private = X25519PrivateKey.from_private_bytes(static_private_raw)
    static_public_raw = static_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    peer_public = X25519PublicKey.from_public_bytes(peer_public_raw)

    chaining = _hash(CONSTRUCTION)
    handshake = _hash(chaining, IDENTIFIER)
    handshake = _hash(handshake, peer_public_raw)

    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public_raw = ephemeral_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    chaining = _kdf(chaining, ephemeral_public_raw, 1)[0]
    handshake = _hash(handshake, ephemeral_public_raw)

    chaining, key = _kdf(chaining, ephemeral_private.exchange(peer_public), 2)
    encrypted_static = _seal(key, 0, static_public_raw, handshake)
    handshake = _hash(handshake, encrypted_static)

    chaining, key = _kdf(chaining, static_private.exchange(peer_public), 2)
    encrypted_timestamp = _seal(key, 0, _tai64n(), handshake)
    handshake = _hash(handshake, encrypted_timestamp)

    sender_index = secrets.randbits(32)
    flags = bytes(tuple(reserved)[:3]) if reserved else b"\x00\x00\x00"
    flags = flags.ljust(3, b"\x00")

    packet = bytearray()
    packet.append(MSG_INITIATION)
    packet.extend(flags)
    packet.extend(struct.pack("<I", sender_index))
    packet.extend(ephemeral_public_raw)
    packet.extend(encrypted_static)
    packet.extend(encrypted_timestamp)
    packet.extend(_mac(_hash(LABEL_MAC1, peer_public_raw), bytes(packet)))
    packet.extend(b"\x00" * 16)

    if len(packet) != INITIATION_SIZE:  # pragma: no cover - structural guard
        raise ValueError(f"initiation is {len(packet)} bytes, expected {INITIATION_SIZE}")
    return bytes(packet), sender_index


def is_response(data: bytes, sender_index: int) -> bool:
    """True when this really is our handshake response and not stray noise."""
    if not data or len(data) < 12 or data[0] != MSG_RESPONSE:
        return False
    return struct.unpack_from("<I", data, 8)[0] == sender_index


# --------------------------------------------------------------------- #
# probing
# --------------------------------------------------------------------- #


class _Listener(asyncio.DatagramProtocol):
    def __init__(self, future: asyncio.Future) -> None:
        self._future = future

    def _settle(self, value: bytes) -> None:
        if not self._future.done():
            self._future.set_result(value)

    def datagram_received(self, data: bytes, addr: object) -> None:
        self._settle(data)

    def error_received(self, exc: Exception) -> None:
        # ICMP port unreachable and friends: treat as a dead endpoint.
        self._settle(b"")

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self._settle(b"")


def _family(host: str) -> int:
    try:
        return socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
    except ValueError:
        return 0


async def handshake_rtt(
    host: str,
    port: int,
    private_key: str,
    peer_public_key: str,
    reserved: Sequence[int] = (0, 0, 0),
    timeout: float = 1.5,
) -> Optional[float]:
    """Round-trip time of one full handshake, in ms. None means no answer."""
    try:
        packet, sender_index = build_initiation(private_key, peer_public_key, reserved)
    except (ValueError, TypeError):
        return None

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    transport: Optional[asyncio.DatagramTransport] = None
    started = 0.0

    try:
        transport, _ = await asyncio.wait_for(
            loop.create_datagram_endpoint(
                lambda: _Listener(future),
                remote_addr=(host, port),
                family=_family(host),
            ),
            timeout=timeout,
        )
        started = time.perf_counter()
        transport.sendto(packet)
        data = await asyncio.wait_for(future, timeout=timeout)
    except (OSError, asyncio.TimeoutError, ValueError):
        return None
    finally:
        if transport is not None:
            transport.close()

    if not is_response(data, sender_index):
        return None
    return round((time.perf_counter() - started) * 1000, 1)


async def stable_handshake(
    host: str,
    port: int,
    private_key: str,
    peer_public_key: str,
    reserved: Sequence[int] = (0, 0, 0),
    timeout: float = 1.5,
    attempts: int = 2,
    gap: float = 0.9,
    retries: int = 1,
) -> Optional[float]:
    """Average RTT across several spaced handshakes, or None if one round fails.

    DPI often lets the first handshake through and kills the session a moment
    later. A single probe cannot see that; a second one a beat later can.

    UDP being UDP, one lost datagram is not evidence of anything, so each round
    gets a second try before the endpoint is written off. Without that retry a
    healthy endpoint on a busy link gets thrown away and the pool stays empty.
    """
    samples: list[float] = []
    for index in range(max(1, attempts)):
        if index:
            await asyncio.sleep(gap)
        rtt: Optional[float] = None
        for attempt in range(max(1, retries + 1)):
            rtt = await handshake_rtt(host, port, private_key, peer_public_key, reserved, timeout)
            if rtt is not None:
                break
            await asyncio.sleep(0.2)
        if rtt is None:
            return None
        samples.append(rtt)
    return round(sum(samples) / len(samples), 1)
