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

Why it changed again: the guess that survived
---------------------------------------------
The picker was correct and the renderer was correct, and iPhone reports kept
arriving anyway. The reason was one line in here. ``normalise_platform`` answered
``android`` to *everything* it did not recognise, including the empty string, so
"the caller said Android" and "the caller said nothing I understand" produced the
same answer - and that answer was the one platform that gets obfuscation keys.

Every path that can lose the platform segment therefore ended in an AmneziaWG
file: a keyboard from before the picker existed (``wg:net:mtn`` with no tail), a
truncated ``callback_data``, a hand-typed deep link, a rename in the alias table.
An Android user in that state gets a working file, so nobody noticed. An iPhone
user gets one their client refuses, and no error either of us can see.

``resolve_platform`` is the honest version: it returns ``None`` when it does not
know, and callers that decide what goes *inside* a config use it and fail safe.
``normalise_platform`` still answers ``DEFAULT`` because dozens of display call
sites need *a* profile and none of them can usefully fail - but it is now only
ever used for that.

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

# Characters that separate a platform name from the noise around it in callback
# data, i18n keys and deep links: ``wg:dev:ios``, ``btn.wg_ios``, ``plat-ios``.
_SEPARATORS: tuple[str, ...] = (":", "-", ".", "/", " ", "|", "=", ",")


def _tokens(value: object) -> list[str]:
    """The words inside a value, so a wrapped platform name is still findable."""
    text = str(value or "").strip().lower()
    for char in _SEPARATORS:
        text = text.replace(char, "_")
    return [part for part in text.split("_") if part]


def resolve_platform(value: object) -> Optional[str]:
    """The platform this value names, or ``None`` when it names nothing.

    Use this - not ``normalise_platform`` - anywhere the answer decides what goes
    inside a config file. ``None`` means "assume nothing", which is a different
    and much safer thing than "assume Android".

    An exact match wins. Failing that the value is split on the separators that
    show up in callback data and i18n keys, so ``wg:dev:ios`` and ``btn.wg_ios``
    both resolve. Single letter aliases (``i``, ``a``, ``w``, ``m``) are honoured
    only as a whole value: finding them inside a token would turn any stray word
    into a platform.
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _ALIASES:
        return _ALIASES[text]
    for token in _tokens(text):
        if len(token) > 1 and token in _ALIASES:
            return _ALIASES[token]
    return None


def is_known(value: object) -> bool:
    """True when ``value`` names a platform we actually support."""
    return resolve_platform(value) is not None


def normalise_platform(value: object) -> str:
    """Any spelling in, one of ``PLATFORMS`` out. Never raises.

    Unrecognised input still answers ``DEFAULT``, because the many display call
    sites need *a* profile and none of them can usefully fail. That fallback is
    exactly why it must not be used to decide file contents - see
    ``resolve_platform`` and ``may_obfuscate``.
    """
    return resolve_platform(value) or DEFAULT


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
    """Whether this platform may receive AmneziaWG obfuscation keys.

    Resolves through ``normalise_platform``, so an unknown value answers for
    Android. Kept for callers that already hold a resolved platform name. If the
    value came from outside - callback data, a database row, a query string - use
    ``may_obfuscate`` instead.
    """
    return profile(platform).supports_amneziawg


def may_obfuscate(value: object) -> bool:
    """Whether obfuscation is safe for a *caller supplied* platform value.

    Fails closed, because the cost of guessing wrong is not symmetric: clean
    WireGuard on Android is a working tunnel with weaker obfuscation, while
    AmneziaWG on an iPhone is a file the client refuses outright. So an
    unrecognised value gets the clean config.
    """
    resolved = resolve_platform(value)
    if resolved is None:
        return False
    return PLATFORMS[resolved].supports_amneziawg


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
    """Which export a platform should get by default: ``awg`` or ``plain``.

    Fails closed for the same reason ``may_obfuscate`` does.
    """
    return "awg" if may_obfuscate(platform) else "plain"


__all__ = [
    "DEFAULT",
    "ORDER",
    "PLATFORMS",
    "PLATFORM_ANDROID",
    "PLATFORM_IOS",
    "PLATFORM_MACOS",
    "PLATFORM_WINDOWS",
    "PlatformProfile",
    "default_platform",
    "emoji",
    "get_dns_servers",
    "get_keepalive",
    "get_mtu",
    "get_platform",
    "is_known",
    "is_supported",
    "kind_for",
    "label_key",
    "list_platforms",
    "may_obfuscate",
    "normalise_platform",
    "prefers_ipv4",
    "profile",
    "resolve_platform",
    "should_include_amnezia_keys",
    "should_include_ipv6",
]
