# AutoVless Update Guide: iOS Support & ProtonVPN

## Summary of Changes

This update fixes three critical issues:

1. **iPhone support**: iOS WireGuard was broken because configs included AmneziaWG-only keys that the official app rejects. Now iOS gets clean, standard WireGuard configs.
2. **Irancell IPv6 bug**: All 6 export buttons had unbracketed IPv6 endpoints like `2001:db8::1:51820` (ambiguous colon). Now all IPv6 endpoints are properly bracketed: `[2001:db8::1]:51820`.
3. **ProtonVPN free configs**: New feature adds real ProtonVPN free tier support (no paid accounts needed). Configs are generated via ProtonVPN API, not hand-written.

## New Files

```
bot/platforms.py        Per-OS config profiles (iOS/Android/Windows)
bot/protonvpn.py        ProtonVPN API client + X25519 key derivation
bot/warpconf.py         Unified config renderer for all OS/family combos
bot/handlers/proton.py  Three-screen Proton flow: location → OS → delivery
bot/locales/proton.py   Persian + English strings for Proton UI
docs/UPDATE.md          This file
```

## Modified Files

```
bot/handlers/pool.py      Added OS selector after operator pick
bot/handlers/warp.py      Updated all 6 export buttons to use warpconf
bot/keyboards.py          Added glass buttons, country grid, OS picker
bot/i18n.py               Registered Proton locale
bot/handlers/__init__.py   Registered Proton router
```

## Deployment Steps

### 1. Pull the feature branch

```bash
cd /path/to/AutoVless
git fetch origin feature/ios-proton-platforms
git checkout feature/ios-proton-platforms
```

### 2. Install new dependencies (if any)

The code adds:
- `nacl` (PyNaCl): For X25519 key derivation

Install it:

```bash
pip install pynacl
```

Verify `aiohttp` and `pyrogram` are already present in `requirements.txt`.

### 3. Test locally

Create a test script `/tmp/test_platforms.py`:

```python
import sys
sys.path.insert(0, '/path/to/AutoVless')

from bot.platforms import get_platform, list_platforms
from bot.warpconf import render_amneziawg_warp_config, bracket_ipv6_endpoint

# Test platform profiles
for prof in list_platforms():
    print(f"{prof.name}: {prof.description}")
    print(f"  MTU: {prof.mtu}")
    print(f"  Supports AmneziaWG: {prof.supports_amneziawg}")
    print()

# Test IPv6 endpoint bracketing (fix for Irancell)
test_endpoint = "2604:cb80::1:51820"
bucketed = bracket_ipv6_endpoint(test_endpoint)
print(f"Original: {test_endpoint}")
print(f"Bracketed: {bucketed}")
assert bucketed == "[2604:cb80::1]:51820", f"Expected bracketed, got {bucketed}"
print("✓ IPv6 bracketing works")

# Test config rendering
android_config = render_amneziawg_warp_config(
    interface_privkey="sPmFz9eS5bY7WZ8N7/8X7N/w/Yq+X8YQ/aR+X8===",
    interface_addr4="10.2.0.2/32",
    interface_addr6="2a07:b944::2:2/128",
    peer_pubkey="1fGFZtHU8r8qwdnron9E80NdvLw5WcUdhPgh7phzQnA=",
    peer_endpoint="195.242.214.66:51820",
    platform="android",
    Jc=3,
    Jmin=1,
    Jmax=3,
    S1=0,
    S2=0,
    S3=0,
    S4=0,
    H1=1,
    H2=2,
    H3=3,
    H4=4,
)
print("\nAndroid WARP config (excerpt):")
print(android_config[:200] + "...")
assert "Jc = 3" in android_config
print("✓ Android AmneziaWG keys included")

ios_config = render_amneziawg_warp_config(
    interface_privkey="sPmFz9eS5bY7WZ8N7/8X7N/w/Yq+X8YQ/aR+X8===",
    interface_addr4="10.2.0.2/32",
    interface_addr6="2a07:b944::2:2/128",
    peer_pubkey="1fGFZtHU8r8qwdnron9E80NdvLw5WcUdhPgh7phzQnA=",
    peer_endpoint="195.242.214.66:51820",
    platform="ios",
)
print("\niOS WireGuard config (excerpt):")
print(ios_config[:200] + "...")
assert "Jc" not in ios_config
print("✓ iOS gets clean WireGuard (no AmneziaWG keys)")

print("\n✅ All tests passed!")
```

Run it:

```bash
python /tmp/test_platforms.py
```

### 4. Deploy to production

Once testing is complete:

```bash
# Merge the feature branch
git checkout main
git merge feature/ios-proton-platforms

# Push to production
git push origin main

# Restart the bot on your VPS
sudo systemctl restart autovless  # or your bot service name
```

## Verification Checklist

- [ ] Pool operators (MTProto, etc.) now ask for OS before generating config
- [ ] WARP export buttons no longer crash (warpconf handles all OS combos)
- [ ] iPhone users can now import WARP configs into WireGuard app
- [ ] IPv6 endpoints are always bracketed: `[2604:cb80::1]:51820`
- [ ] New ProtonVPN button works: location picker → OS picker → config delivery
- [ ] iOS ProtonVPN configs have no Jc/S1/H1 keys
- [ ] Android/Windows ProtonVPN configs include all AmneziaWG keys
- [ ] Irancell users can connect with the new bracketed IPv6 endpoints

## Rollback (if needed)

If something breaks:

```bash
git revert HEAD  # Revert the last commit
git push origin main
sudo systemctl restart autovless
```

Or revert to the commit before the merge:

```bash
git checkout <commit-hash-before-merge>
git push origin main -f
sudo systemctl restart autovless
```

## Questions?

Check the code comments in:
- `bot/platforms.py`: Why iOS doesn't support AmneziaWG
- `bot/warpconf.py`: IPv6 bracketing fix
- `bot/protonvpn.py`: X25519 key derivation from Ed25519 seed
