"""Per-operating-system config architecture.

Why this module exists
----------------------
Every WARP config the bot handed out was AmneziaWG, and that single fact is why
iPhone users reported that "the WireGuard protocol does not run". It is not
filtering and it is not the endpoint. An AmneziaWG file carries ``Jc``, ``Jmin``,
``Jmax``, ``S1``-``S4``, ``H1``-``H4`` and sometimes ``I1`` inside
``[Interface]``, and the official WireGuard app for iOS is a strict INI parser:
it meets one key it does not recognise, decides the file is not a WireGuard
config, and refuses all of it. No error the user can act on, just a tunnel that
never comes up.

So the platform is asked before a config is rendered and never guessed. iOS gets
clean standard WireGuard. Android gets the full obfuscation. Windows gets the
same as Android because its clients understand it. macOS is grouped with iOS
because the app is the same codebase and the same strict parser.

Everything in here is a lookup. The rendering itself lives in ``bot.warpconf``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PlatformProfile:
    """A platform (OS plus its usual client) and its config generation rules."""

    name: str  # 'ios', 'android', 'windows', 'macos'
    mtu: int  # Default MTU for this platform
    keepalive: Optional[int]  # PersistentKeepalive in seconds, or None
    dns_servers: List[str]  # Preferred DNS servers
    supports_amneziawg: bool  # Whether AmneziaWG obfuscation keys may be emitted
    supports_ipv6: bool  # Whether IPv6 interface addresses are included
    description: str  # Display name
    emoji: str  # Icon for the picker
    min_clients: Dict[str, str] = field(default_factory=dict)
    # True when an IPv4 endpoint should be preferred if the pool holds one. The
    # official iOS client is fine with IPv6 endpoints on wifi and unreliable on
    # cellular, so IPv4 is the safer default when both exist.
    prefer_ipv4: bool = False
    # i18n key for this platform's picker button.
    label_key: str = ""


# === Profile definitions ===

PLATFORM_IOS = PlatformProfile(
    name="ios",
    mtu=1280,
    keepalive=25,
    dns_servers=["1.1.1.1", "1.0.0.1"],
    # Critical. WireGuard for iOS rejects a file that carries unknown
    # [Interface] keys, so obfuscation is off and stays off for this platform.
    supports_amneziawg=False,
    supports_ipv6=True,
    description="iPhone / iPad (WireGuard, Streisand)",
    emoji="\U0001f34f",
    min_clients={"wireguard": "1.0.0"},
    prefer_ipv4=True,
    label_key="btn.wg_ios",
)

PLATFORM_ANDROID = PlatformProfile(
    name="android",
    mtu=1280,
    keepalive=25,
    dns_servers=["1.1.1.1", "1.0.0.1"],
    supports_amneziawg=True,
    supports_ipv6=True,
    description="Android (AmneziaVPN, WG Tunnel, Hiddify)",
    emoji="\U0001f916",
    min_clients={"amneziawg": "1.0.0", "wireguard": "1.0.0"},
    prefer_ipv4=False,
    label_key="btn.wg_android",
)

PLATFORM_WINDOWS = PlatformProfile(
    name="windows",
    mtu=1280,
    keepalive=25,
    dns_servers=["1.1.1.1", "1.0.0.1"],
    supports_amneziawg=True,
    supports_ipv6=True,
    description="Windows (AmneziaVPN, Hiddify)",
    emoji="\U0001fa9f",
    min_clients={"amneziawg": "0.1.0", "wireguard": "0.5.3"},
    prefer_ipv4=False,
    label_key="btn.wg_windows",
)

PLATFORM_MACOS = PlatformProfile(
    name="macos",
    mtu=1280,
    keepalive=25,
    dns_servers=["1.1.1.1", "1.0.0.1"],
    # Same strict parser as iOS: the macOS WireGuard app is the same codebase.
    supports_amneziawg=False,
    supports_ipv6=True,
    description="macOS (WireGuard, Streisand)",
    emoji="\U0001f4bb",
    min_clients={"wireguard": "1.0.0"},
    prefer_ipv4=True,
    label_key="btn.wg_mac",
)

PLATFORMS: Dict[str, PlatformProfile] = {
    "ios": PLATFORM_IOS,
    "android": PLATFORM_ANDROID,
    "windows": PLATFORM_WINDOWS,
    "macos": PLATFORM_MACOS,
}

# The order the picker shows them in. iPhone first: it is the one platform where
# picking wrong means the file does not load at all.
ORDER: tuple[str, ...] = ("ios", "android", "windows", "macos")

DEFAULT = "android"

# Spellings that arrive from callback data, older keyboards and user text.
_ALIASES: Dict[str, str] = {
    "ios": "ios",
    "iphone": "ios",
    "ipad": "ios",
    "apple": "ios",
    "i": "ios",
    "android": "android",
    "droid": "android",
    "a": "android",
    "windows": "windows",
    "win": "windows",
    "pc": "windows",
    "w": "windows",
    "macos": "macos",
    "mac": "macos",
    "osx": "macos",
    "m": "macos",
}


def normalise_platform(value: object) -> str:
    """Any spelling in, one of ``PLATFORMS`` out. Never raises."""
    text = str(value or "").strip().lower()
    return _ALIASES.get(text, DEFAULT)


def default_platform() -> str:
    return DEFAULT


def get_platform(name: str) -> Optional[PlatformProfile]:
    """Retrieve a platform profile by exact name, or ``None``."""
    return PLATFORMS.get(str(name or "").strip().lower())


def profile(name: object) -> PlatformProfile:
    """Like ``get_platform`` but always returns something usable."""
    return PLATFORMS[normalise_platform(name)]


def list_platforms() -> List[PlatformProfile]:
    """Every profile, in picker order."""
    return [PLATFORMS[name] for name in ORDER]


def is_supported(name: object) -> bool:
    return str(name or "").strip().lower() in PLATFORMS


def should_include_amnezia_keys(platform: str) -> bool:
    """Whether this platform may receive AmneziaWG obfuscation keys."""
    return profile(platform).supports_amneziawg


def get_mtu(platform: str) -> int:
    return profile(platform).mtu


def get_dns_servers(platform: str) -> List[str]:
    return list(profile(platform).dns_servers)


def get_keepalive(platform: str) -> Optional[int]:
    return profile(platform).keepalive


def should_include_ipv6(platform: str) -> bool:
    return profile(platform).supports_ipv6


def prefers_ipv4(platform: str) -> bool:
    return profile(platform).prefer_ipv4


def emoji(platform: str) -> str:
    return profile(platform).emoji


def label_key(platform: str) -> str:
    return profile(platform).label_key or "btn.wg_android"


def kind_for(platform: str) -> str:
    """Which export a platform should get by default: ``awg`` or ``plain``."""
    return "awg" if should_include_amnezia_keys(platform) else "plain"
