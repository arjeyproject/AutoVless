# Serving AutoVless from your own domain

This is the runbook for `prostoreshop.site`, and the reason the subscription links
were broken.

## The problem, stated once

A panel lives at `<script>.<subdomain>.workers.dev`. The *tunnel* to it does not
need that hostname to resolve, because the client dials a clean Cloudflare IP
directly and carries the hostname in a header - which is why configs worked. The
*subscription* does need it to resolve, because the client has to fetch a URL. And
`workers.dev` is DNS-poisoned on essentially every Iranian network.

So the subscription came back empty, the client showed a profile with no servers
in it, and it looked exactly like a dead config. It was never the config.

The fix is a gateway: the bot serves the same list from your own domain, reading
the endpoints out of its own database - the same rows the autopilot refreshes - so
nothing goes stale and nothing depends on `workers.dev` being reachable.

## 1. DNS

Point the domain at the box the bot runs on. An A record, proxy **off** if the
domain sits on Cloudflare:

```
A    prostoreshop.site        <your server ip>    (DNS only, grey cloud)
A    www.prostoreshop.site    <your server ip>    (DNS only, grey cloud)
```

Leave the orange cloud off. Proxying the gateway through Cloudflare puts a
Cloudflare hostname back in front of your subscription, and that is the hostname
class we are getting away from.

## 2. TLS in front of the bot

The API listens on `127.0.0.1:8088` by default. Caddy is two lines and gets a
certificate on its own:

```
# /etc/caddy/Caddyfile
prostoreshop.site {
    reverse_proxy 127.0.0.1:8088
}
```

```bash
sudo apt install -y caddy
sudo systemctl reload caddy
```

Bind the API to localhost so nothing but Caddy can reach it:

```
API_HOST=127.0.0.1
API_PORT=8088
```

## 3. Environment

Add to `.env`:

```ini
# The domain everything user-facing is served from. This one value switches the
# subscription gateway on.
PUBLIC_URL=https://prostoreshop.site

# The mini app. Same origin, so the page and its API share one certificate.
WEBAPP_URL=https://prostoreshop.site

# How long a download link stays valid. It carries a private key, so it is a
# single sitting rather than a bookmark.
DOWNLOAD_TTL=3600

# Shadowsocks, the third protocol. Leave it off until the worker bundle in front
# of it carries the inbound - see the section at the bottom.
SS=0
SS_PATH=/ss
```

Nothing else changes. `PUBLIC_URL` is read at request time, so no other setting
has to move, and if you leave it blank every link falls back to the worker exactly
as before.

## 4. Restart and verify

```bash
docker compose up -d --build          # or: systemctl restart autovless
curl -s https://prostoreshop.site/api/health | jq
```

You want `"gateway": true` and `"origin": "https://prostoreshop.site"`. If gateway
is false, `PUBLIC_URL` did not reach the process.

Then, as a user with a panel, open the bot: **Panel → Subscription**. The links
are now on your domain and carry a note saying why. Fetch one to be sure:

```bash
curl -s "https://prostoreshop.site/sub/<token>" | head -c 80 | base64 -d | head -3
```

That should print `vless://` lines.

## What each new route does

| Route | Purpose |
| --- | --- |
| `/sub/<token>` | VLESS subscription, base64. What a client imports. |
| `/sub/<token>/mix` | Every protocol in one subscription. |
| `/sub/<token>/raw` | The same links, unencoded, for eyeballing. |
| `/sub/<token>/trojan`, `/ss` | One protocol only. |
| `/sub/<token>/clash`, `/singbox` | Ready client profiles, all protocols, latency tested. |
| `/sub/<token>/fragment`, `/noise` | Xray profiles: fragmentation, and fragmentation plus UDP noise. |
| `/sub/free/<token>` | The same service for a user on the shared free server. |
| `/dl/<ticket>` | One file as a real download. Short lived and signed. |

Tokens are `<user id in hex>.<hmac>`, signed under `SECRET_KEY` **and** the panel
uuid. Delete a panel and build a new one and every old link stops verifying on its
own, because the uuid it was signed against no longer exists. Nothing is stored:
the token is the request.

## Why downloads used to do nothing

The mini app built the file in JavaScript as a Blob and clicked a hidden
`<a download>`. Telegram's in-app browser refuses that, and on iOS it refuses it
silently - no error, no file, nothing on screen. Every file now has a real URL with
a real `Content-Disposition`, opened through `openLink` so the operating system
handles it. That is also what puts a `.conf` in front of the WireGuard app's
importer on an iPhone.

## Why the iPhone could not connect to WireGuard

Three separate causes, all fixed:

1. **The file would not load at all.** The official WireGuard app for iOS is a
   strict INI parser. AmneziaWG's `Jc`, `S1`, `H1`... inside `[Interface]` make it
   reject the whole file. iOS and macOS were already getting clean standard
   WireGuard for this reason - that part was working.
2. **The tunnel came up and carried nothing.** `AllowedIPs` was always
   `0.0.0.0/0, ::/0`. An identity with no IPv6 address then claims the entire IPv6
   internet through an interface that cannot source from it. Android shrugs; the
   Apple client installs the route, and every AAAA lookup races into a black hole
   first. The route is now claimed only for families the interface actually holds.
3. **The endpoint was on a port the carrier drops.** The pool legitimately holds
   WARP endpoints on a dozen ports, and a scan from your server cannot tell which
   ones an Iranian carrier drops, because the scan does not run over that carrier.
   Apple platforms now prefer the four ports the official WARP client itself dials
   - 2408, 500, 4500, 1701 - and fall back to the measured ranking only if the pool
   has none of them. A preference, never a filter.

On top of that the WARP screen in the mini app now shows the config as a **QR
code** for Apple devices, because WireGuard imports a tunnel from a QR directly and
that path involves no file handling at all. It is the most reliable route onto an
iPhone by a distance.

## The 15 second timeout is gone

Requests had a client-side deadline of 15s. Applying fresh IPs and registering a
WARP identity both legitimately take longer, so the deadline was not protecting
anyone from a hung server - it was cancelling the user's own work and then
reporting a timeout that had not happened. There is no client deadline any more.

The overlay that deadline was really protecting has its own escape hatch instead:
after twelve seconds it offers a dismiss button, so a slow request gives the screen
back without being killed.

## Shadowsocks, the third protocol

`bot/shadowsocks.py` and `worker/shadowsocks.js` add Shadowsocks AEAD
(`aes-256-gcm`) over WebSocket alongside VLESS and Trojan. It is a genuinely
different shape on the wire: no version byte, no hex preamble, nothing in the clear
- the first byte is one of 32 random salt bytes and everything after it is
ciphertext. A classifier trained on the other two has nothing to match.

It is dispatched by WebSocket path (`SS_PATH`) rather than sniffed, because random
bytes are indistinguishable from a VLESS header by inspection and a wrong guess is
a silent auth failure.

The crypto is tested, and against an independent implementation rather than itself:

```bash
node scripts/test-shadowsocks.mjs
```

Eleven checks, including agreement with a client built on `node:crypto`, and the
key `bot/shadowsocks.py` derives matching `EVP_BytesToKey` byte for byte.

**It is off by default and should stay off until the inbound is inlined into
`worker/vless-worker.js`.** The bot side is finished - links, Clash blocks,
sing-box outbounds, the `SS_KEY` binding - but the worker bundle in front of it does
not answer `/ss` yet, and turning `SS=1` on before that would hand users links that
cannot connect. That splice is one focused change to the bundle and wants to be
made against a test panel first, not against everybody's live worker.

## Loose end, named on purpose

`worker/vless-worker-v2.js` has no `mix` or `trojan` route, so those paths quietly
return the plain VLESS subscription. It is not the bundle that ships - `WORKER_FILE`
points at `vless-worker.js` - so nothing in production is affected, and it was left
alone rather than half-fixed.
