"""Compatibility export for the second-generation network scanners."""

from .scanner_v2 import CleanIPScanner, ProxyIPScanner, is_cloudflare, proxy_scanner, scanner

__all__ = [
    "CleanIPScanner",
    "ProxyIPScanner",
    "is_cloudflare",
    "scanner",
    "proxy_scanner",
]
