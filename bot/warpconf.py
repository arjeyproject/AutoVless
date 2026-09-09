"""Config rendering that is correct for all OS/family combos.

Why this exists
----------------
WARP and Screensaver configs are rendered to INI format with sections like
[Interface] and [Peer]. Before this module, every renderer (WARP export button,
Screensaver button, etc.) had its own copy of the rendering logic, and they did
not agree on things like:

  - Whether IPv6 endpoints use brackets: ``[2604:cb80::1]:51820`` or not
  - Whether AmneziaWG obfuscation keys (Jc, S1-S4, H1-H4, I1) appear in output
  - Whether the endpoint is bracketed for IPv6 or raw
  - MTU per family (IPv4 vs IPv6)
  - DNS servers per OS

This module centralizes rendering and applies platform-aware rules:

  - iOS: clean standard WireGuard (no Amnezia keys)
  - Android: full AmneziaWG with all obfuscation keys
  - Windows: AmneziaWG with all keys

The result: every button hands out a config that actually works on the target OS.
"""

import ipaddress
from typing import Dict, List, Optional
from .platforms import PlatformProfile, get_platform, should_include_amnezia_keys


def bracket_ipv6_endpoint(endpoint: str) -> str:
    """Ensure IPv6 endpoints are bracketed for WireGuard syntax.
    
    WireGuard syntax: [2001:db8::1]:51820 for IPv6, 1.2.3.4:51820 for IPv4.
    Irancell bug: shipped unbracketed IPv6 like 2001:db8::1:51820 (colon is ambiguous).
    """
    if ":" not in endpoint:
        return endpoint  # Pure IPv4 or hostname
    
    parts = endpoint.rsplit(":", 1)  # Split from the right to separate port
    if len(parts) != 2:
        return endpoint
    
    host, port = parts
    try:
        addr = ipaddress.ip_address(host)
        if isinstance(addr, ipaddress.IPv6Address):
            return f"[{host}]:{port}"
        else:
            return endpoint
    except ValueError:
        # Not an IP, maybe a hostname
        return endpoint


def render_wg_config(
    interface_privkey: str,
    interface_addrs: List[str],  # e.g., ["10.2.0.2/32", "2a07:b944::2:2/128"]
    peer_pubkey: str,
    peer_endpoint: str,
    allowed_ips: List[str],  # e.g., ["0.0.0.0/0", "::/0"]
    dns_servers: Optional[List[str]] = None,
    platform: str = "android",
    amnezia_keys: Optional[Dict[str, any]] = None,
    mtu: Optional[int] = None,
) -> str:
    """Render a complete WireGuard config INI.
    
    Args:
        interface_privkey: Base64 WireGuard private key
        interface_addrs: Interface addresses (IPv4 and/or IPv6)
        peer_pubkey: Peer's base64 public key
        peer_endpoint: Peer endpoint, automatically bracketed for IPv6
        allowed_ips: What IPs are routed through this peer
        dns_servers: Custom DNS servers (platform default if None)
        platform: 'ios', 'android', or 'windows'
        amnezia_keys: Dict of AmneziaWG keys (ignored on iOS)
        mtu: Custom MTU (platform default if None)
    
    Returns:
        INI format config string.
    """
    prof = get_platform(platform)
    if not prof:
        platform = "android"  # fallback
        prof = get_platform(platform)
    
    if not dns_servers:
        dns_servers = prof.dns_servers
    if not mtu:
        mtu = prof.mtu
    
    # Always bracket IPv6 endpoints
    peer_endpoint = bracket_ipv6_endpoint(peer_endpoint)
    
    # Build [Interface] section
    interface_lines = [
        f"PrivateKey = {interface_privkey}",
    ]
    
    for addr in interface_addrs:
        interface_lines.append(f"Address = {addr}")
    
    # DNS
    if dns_servers:
        interface_lines.append(f"DNS = {', '.join(dns_servers)}")
    
    # MTU
    interface_lines.append(f"MTU = {mtu}")
    
    # Add AmneziaWG keys ONLY if platform supports them
    if should_include_amnezia_keys(platform) and amnezia_keys:
        for key, value in amnezia_keys.items():
            interface_lines.append(f"{key} = {value}")
    
    # Build [Peer] section
    peer_lines = [
        f"PublicKey = {peer_pubkey}",
        f"Endpoint = {peer_endpoint}",
    ]
    for ip in allowed_ips:
        peer_lines.append(f"AllowedIPs = {ip}")
    
    # Combine into INI
    config = "[Interface]\n" + "\n".join(interface_lines)
    config += "\n\n[Peer]\n" + "\n".join(peer_lines)
    return config


def render_amneziawg_warp_config(
    interface_privkey: str,
    interface_addr4: str,
    interface_addr6: str,
    peer_pubkey: str,
    peer_endpoint: str,
    platform: str = "android",
    use_custom_dns: bool = True,
    custom_dns: Optional[List[str]] = None,
    mtu: Optional[int] = None,
    **amnezia_params,
) -> str:
    """Render an AmneziaWG WARP config (for Android/Windows).
    
    Args:
        interface_privkey: Base64 private key
        interface_addr4: IPv4 interface address (e.g., "10.2.0.2/32")
        interface_addr6: IPv6 interface address (e.g., "2a07:b944::2:2/128")
        peer_pubkey: Base64 public key of peer
        peer_endpoint: IP:port of peer
        platform: 'android' or 'windows'
        use_custom_dns: Whether to use custom DNS
        custom_dns: Custom DNS servers
        mtu: Custom MTU
        amnezia_params: Additional AmneziaWG keys (Jc, Jmin, Jmax, S1-S4, H1-H4, I1)
    
    Returns:
        INI format config.
    """
    prof = get_platform(platform)
    if not prof or not prof.supports_amneziawg:
        # Fallback to Android
        prof = get_platform("android")
    
    if custom_dns is None:
        custom_dns = prof.dns_servers
    if mtu is None:
        mtu = prof.mtu
    
    # Bracket IPv6 endpoint
    peer_endpoint = bracket_ipv6_endpoint(peer_endpoint)
    
    # Build [Interface]
    interface_lines = [
        f"PrivateKey = {interface_privkey}",
        f"Address = {interface_addr4}, {interface_addr6}",
    ]
    
    if use_custom_dns and custom_dns:
        interface_lines.append(f"DNS = {', '.join(custom_dns)}")
    
    interface_lines.append(f"MTU = {mtu}")
    
    # Add all AmneziaWG keys
    for key in ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1"]:
        if key in amnezia_params:
            interface_lines.append(f"{key} = {amnezia_params[key]}")
    
    # Build [Peer]
    peer_lines = [
        f"PublicKey = {peer_pubkey}",
        f"Endpoint = {peer_endpoint}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
    ]
    
    config = "[Interface]\n" + "\n".join(interface_lines)
    config += "\n\n[Peer]\n" + "\n".join(peer_lines)
    return config
