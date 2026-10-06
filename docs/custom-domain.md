# Why every config showed -1 in Iran, and the fix

## Root cause

Every VLESS / Trojan / Shadowsocks config carried `<script>.<sub>.workers.dev`
as TLS SNI and WebSocket `Host`. Iranian DPI filters the `workers.dev` SNI (and
the plain `Host` header on port 80), so the handshake dies no matter how clean
the entry IP is. The bot's own acceptance check runs from the VPS abroad, where
workers.dev is fine, so it kept approving configs that could never ping in Iran.

## Fix

If the user's Cloudflare account has any active zone, the bot now attaches the
panel worker to `<label>.<zone>` with Workers Custom Domains and uses that
hostname as SNI and Host everywhere (links, subscriptions, Clash, sing-box,
fragment JSON). Cloudflare routes on SNI, so clean IPs keep working as the
entry point.

* New builds: automatic.
* Existing panels: moved on the next **Apply fresh clean IPs** or autopilot
  pass, same uuid, same gateway subscription link.
* No domain on the account: the panel stays on workers.dev and the bot tells
  the user to add one.

## Token

The token button now also requests **Zone > Workers Routes: Edit**. Old tokens
without it keep working on workers.dev; users need a new token to move.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `CUSTOM_DOMAIN` | `true` | `false` keeps every panel on workers.dev |
| `CUSTOM_ZONE` | blank | pin one zone name instead of the shortest active one |

## WARP / WireGuard note

A WireGuard client shows "connected" even when no handshake ever completed, so
"connected but no data" means the endpoint is dropped on the user's network.
The WARP scanner also runs from the VPS abroad. Feed the pool with endpoints
scanned from inside Iran (WarpEP) through Admin > Pool > Manual, and prefer the
AmneziaWG file with I1 (awg2) on AmneziaVPN 4.8+.
