"""Per-operating-system config architecture.

Why this module exists
----------------------
Until now every WARP config the bot handed out was AmneziaWG, and that is the
single reason iPhone users reported that "nothing works". It is not filtering and
it is not the endpoint: an AmneziaWG file carries ``Jc``, ``Jmin``, ``Jmax``,
``S1``-``S4``, ``H1``-``H4`` and sometimes ``I1`` inside ``[Interface]``, and the
official WireGuard app for iOS is a strict parser. It sees an unknown key and
refuses the entire file.

This module defines how each OS gets its own "flavor" of config. iOS gets clean
standard WireGuard. Android gets full AmneziaWG for advanced obfuscation. Windows
gets AmneziaWG or clean depending on context.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class PlatformProfile:
    """A platform (OS + app) and its config generation rules."""
    
    name: str  # 'ios', 'android', 'windows'
    mtu: int  # Default MTU for this platform
    keepalive: Optional[int]  # Keepalive interval in seconds, or None
    dns_servers: List[str]  # Preferred DNS servers
    supports_amneziawg: bool  # Whether to include AmneziaWG obfuscation keys
    supports_ipv6: bool  # Whether to include IPv6 addresses
    description: str  # Display name
    emoji: str  # Icon for UI
    min_clients: Dict[str, int]  # Min client versions per app


# === Profile Definitions ===

PLATFORM_IOS = PlatformProfile(
    name='ios',
    mtu=1280,
    keepalive=25,
    dns_servers=['1.1.1.1'],
    supports_amneziawg=False,  # Critical: WireGuard iOS rejects unknown [Interface] keys
    supports_ipv6=True,
    description='iPhone/iPad (WireGuard app)',
    emoji='🍎',
    min_clients={
        'wireguard': '1.0.0',
    },
)

PLATFORM_ANDROID = PlatformProfile(
    name='android',
    mtu=1420,
    keepalive=25,
    dns_servers=['1.1.1.1', '8.8.8.8'],
    supports_amneziawg=True,  # Android apps fully support AmneziaWG
    supports_ipv6=True,
    description='Android (WireGuard, Wireguard Go, or AmneziaWG apps)',
    emoji='🤖',
    min_clients={
        'wireguard': '1.0.0',
        'wireguardgo': '1.0.17',
        'amneziawg': '1.0.0',
    },
)

PLATFORM_WINDOWS = PlatformProfile(
    name='windows',
    mtu=1420,
    keepalive=25,
    dns_servers=['1.1.1.1'],
    supports_amneziawg=True,  # Windows clients support AmneziaWG
    supports_ipv6=True,
    description='Windows (WireGuard or AmneziaWG)',
    emoji='🪟',
    min_clients={
        'wireguard': '0.5.3',
        'amneziawg': '0.1.0',
    },
)

# Lookup table
PLATFORMS = {
    'ios': PLATFORM_IOS,
    'android': PLATFORM_ANDROID,
    'windows': PLATFORM_WINDOWS,
}


def get_platform(name: str) -> Optional[PlatformProfile]:
    """Retrieve a platform profile by name."""
    return PLATFORMS.get(name.lower())


def list_platforms() -> List[PlatformProfile]:
    """Return all available platform profiles."""
    return list(PLATFORMS.values())


def should_include_amnezia_keys(platform: str) -> bool:
    """Check if a given platform should include AmneziaWG obfuscation keys."""
    prof = get_platform(platform)
    return prof.supports_amneziawg if prof else False


def get_mtu(platform: str) -> int:
    """Get the recommended MTU for a platform."""
    prof = get_platform(platform)
    return prof.mtu if prof else 1420


def get_dns_servers(platform: str) -> List[str]:
    """Get the recommended DNS servers for a platform."""
    prof = get_platform(platform)
    return prof.dns_servers if prof else ['1.1.1.1']


def get_keepalive(platform: str) -> Optional[int]:
    """Get the recommended keepalive interval for a platform."""
    prof = get_platform(platform)
    return prof.keepalive if prof else None


def should_include_ipv6(platform: str) -> bool:
    """Check if a platform should include IPv6 addresses."""
    prof = get_platform(platform)
    return prof.supports_ipv6 if prof else True
