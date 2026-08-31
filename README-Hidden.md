# AutoVless

A Telegram bot that builds a private VLESS panel **on each user's own Cloudflare account**.
The user pastes an API token, the bot scans for clean Cloudflare edge IPs and working
proxyIP relays, deploys a Worker, verifies the tunnel actually carries traffic, and hands
back a full set of configs on port 443 (TLS) and port 80.

From then on the configs maintain themselves. Nobody has to press rebuild.

Built so people in Iran can reach an open internet. Free, no subscriptions, no resellers.

ربات تلگرامی که روی اکانت کلادفلر خود کاربر یک پنل VLESS می‌سازد، آی‌پی تمیز و پروکسی‌آی‌پی سالم
اسکن می‌کند و بعد از آن، بدون هیچ کاری از طرف کاربر، تازه‌ترین آی‌پی‌های تمیز را روی همان لینک
اشتراک سوار می‌کند.

---

## How clean IPs stay clean

This is the part most tools get wrong. Finding a good address is easy; keeping it in front
of the configs people already hold is the hard half. Three layers do it, and they overlap
on purpose:

1. **The scanner** sweeps each port on its own until that port holds enough verified
   addresses. Every candidate is probed twice through `/cdn-cgi/trace`, so latency *and*
   jitter are real, and the score punishes wobble harder than slowness. Failed live checks
   demote an address; the pool is trimmed per port, never globally.
2. **The Worker** blends fresh addresses into the subscription it serves. Public clean-IP
   lists are fetched through the edge cache on each refresh window, so pressing *Update*
   in v2rayNG is enough to pick up today's entry points. Self-healing hostnames ride along
   too: their DNS is maintained upstream, so that config outlives every raw IP in the list.
3. **The autopilot** re-uploads each panel's Worker in the background with the current best
   endpoints. Same script, same uuid, same subscription URL. Users are never asked to do
   anything, and `Apply fresh clean IPs` in the panel screen runs the same job on demand.

## What it does

- **Glass panel UI**: every screen is an inline keyboard, fully bilingual (فارسی / English),
  right-to-left correct on every client
- **Two-step Cloudflare onboarding**: sign-up button, then a token button with the exact
  permissions pre-selected (Workers Scripts edit, Account read, Zone read, DNS edit)
- **Clean IP engine**: curated lists, self-healing hostnames and a weighted random sweep of
  Cloudflare's prefixes, all verified with real requests that also reveal the edge colo
- **proxyIP scanner**: finds relays that forward TCP to the Cloudflare edge, rejects anything
  resolving into a Cloudflare prefix (a Worker cannot dial those), and keeps a self-healing
  pool. Every panel ships with an ordered failover chain of relays
- **Automatic Worker deploy**: uploads a real VLESS-over-WebSocket Worker to the user's
  account, enables `workers.dev`, mounts the fastest clean IPs onto the configs
- **Health gate**: a panel is reported ready once the Worker proves it can open an outbound
  socket. Dead relays are demoted automatically
- **Subscription served by the Worker itself**: base64, raw, Clash / Mihomo, sing-box
- **Apps and downloads**: a platform picker where every app name is a tappable link to
  Google Play, the App Store or the project's release page
- **Panel management**: QR code, subscription links, individual configs, live ping test that
  demotes dead entries, one-tap clean IP apply, rescan, rebuild, delete
- **WARP / WireGuard generator** with AmneziaWG obfuscation, and a vless link converter
- **Advanced admin panel**: stats, user search with ban controls, broadcast, forced-channel
  lock, scan engine and autopilot controls, feature toggles, event log, database backup

## Requirements

- A Linux server with 1 vCPU and 1 GB RAM (defaults are tuned for exactly this)
- Docker 20.10+ with the compose plugin
- A bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram id (from [@userinfobot](https://t.me/userinfobot))

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/arjeyproject/AutoVless/main/install.sh)
```

The installer pulls the repo into `/opt/autovless`, asks for the bot token and admin id,
writes `.env`, builds the image, and starts the stack.

Manual route:

```bash
git clone https://github.com/arjeyproject/AutoVless.git /opt/autovless
cd /opt/autovless
cp .env.example .env && nano .env      # set BOT_TOKEN and ADMIN_IDS
docker compose up -d --build
docker compose logs -f
```

## Upgrading

```bash
cd /opt/autovless
git pull
docker compose up -d --build
docker compose logs -f
```

The database migrates itself on boot, so nothing is lost. Existing panels were deployed
with the old Worker, and the autopilot replaces them on its own within a few cycles. To do
it immediately, open the admin panel and use **Scan engine → Push IPs to every panel**.

One caveat: a panel can only be refreshed if its Cloudflare token was stored
(`STORE_TOKENS=true`). Panels without one keep working, but their users have to press
**Rebuild panel** once.

## Configuration

Everything lives in `.env`; the only required values are `BOT_TOKEN` and `ADMIN_IDS`.
The file is commented in full. The knobs that matter most:

| Key | Default | Meaning |
| --- | --- | --- |
| `TLS_CONFIG_COUNT` / `HTTP_CONFIG_COUNT` | `4` / `2` | Configs per panel, per port group |
| `SCAN_WAVES` | `3` | Extra passes per port when the pool is thin |
| `SCAN_MIN_VERIFIED` | `8` | Verified addresses each port aims to hold |
| `VERIFY_PROBES` | `2` | Probes per candidate; the spread becomes jitter |
| `CLEAN_DOMAINS` | four community hostnames | Self-healing entry points |
| `SUB_SOURCES` | `CLEAN_IP_SOURCES` | Lists the Worker blends in live |
| `SUB_REFRESH` | `300` | Seconds those lists stay cached at the edge |
| `AUTOPILOT` | `true` | Background re-apply of clean IPs to live panels |
| `AUTOPILOT_INTERVAL` / `AUTOPILOT_BATCH` | `900` / `6` | Cycle timing and panels per cycle |
| `AUTOPILOT_MAX_AGE` | `21600` | Age at which a panel is queued for refresh |
| `PROXY_PER_PANEL` | `4` | Relays baked into each panel as a failover chain |
| `WARP_SCAN_ATTEMPTS` | `2` | Spaced handshakes a WARP endpoint must answer |
| `STORE_TOKENS` | `true` | Required for rebuild, delete and the autopilot |

Tokens are encrypted with a key derived from `SECRET_KEY`. If you leave `SECRET_KEY` empty,
one is generated on first run and stored in `data/.secret`.

## How the config chain works

```
client  ──►  clean Cloudflare IP or hostname : 443 or 80
                     │   (SNI / Host = <script>.<subdomain>.workers.dev)
                     ▼
              Cloudflare edge
                     │
                     ▼
           the user's own Worker
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
  direct socket            proxyIP relay
  (most of the web)   (destinations behind Cloudflare)
```

The address field carries the entry point, while `Host` and `sni` carry the Worker hostname.
That is why swapping in a faster address never breaks the config: only the door changes.

The Worker tries the destination directly first. If the handshake fails, or the socket
returns nothing at all, it walks the relay chain in order, replaying everything the client
has already sent so the next relay joins the session at its first byte rather than halfway
through. That second path is not optional: Cloudflare blocks Worker sockets to its own
addresses, so without a live relay every Cloudflare-fronted site looks dead.

## Worker endpoints

Everything is namespaced under the panel UUID, so nothing is guessable.

| Path | Returns |
| --- | --- |
| `/<uuid>` | base64 subscription, blended live |
| `/<uuid>/raw` | plain `vless://` links |
| `/<uuid>/clash` | Clash / Mihomo YAML |
| `/<uuid>/singbox` | sing-box JSON |
| `/<uuid>/endpoints` | the exact entry points being served right now |
| `/<uuid>/health` | build stamp, endpoint, hostname and relay counts, serving colo |
| `/<uuid>/probe` | live outbound socket test, per relay |

`?proxyip=host:port` on the WebSocket URL overrides the relay chain for one session, which
is the fastest way to test a relay by hand. `?fresh=0` on a subscription URL disables live
blending and returns only the addresses the bot verified, which is useful when debugging.

## Troubleshooting configs that show `-1ms`

1. Tap **Live ping test** in the panel screen. Anything marked ❌ is demoted from the pool
   on the spot, then hit **Apply fresh clean IPs**.
2. Open `https://<host>/<uuid>/probe`. If `ok` is false the Worker cannot open sockets at
   all: the account is brand new or the script was uploaded without the runtime bindings.
   Rebuild the panel.
3. If `usable_relays` is `0`, every relay in the chain is dead. Run a relay sweep from the
   admin panel, or pin a known good one in `PROXY_IP`.
4. If the probe is healthy but the client still fails, the entry address is blocked on that
   network. Try the 🟡 port 80 configs, and the 🌀 hostname config: it is the last one to
   go down.
5. On mobile data, port 80 usually behaves better; on fixed lines, 443 usually wins.

## Project layout

```
bot/
  main.py          entrypoint and dispatcher wiring
  config.py        environment-driven settings
  db.py            SQLite storage, encrypted token vault, self-migrating schema
  proxies.py       proxyIP relay pool
  scanner.py       clean IP and proxyIP scanners
  deploy.py        token to live, health-checked Worker, plus in-place refresh
  autopilot.py     rolling re-apply of clean IPs to every live panel
  vless.py         links, Clash, sing-box
  apps.py          client app catalogue with real download links
  warp.py          WARP / WireGuard provisioning
  warpscan.py      WARP endpoint engine
  wireguard.py     hand-rolled handshake used to prove an endpoint is alive
  screens.py       shared screen composition
  keyboards.py     inline keyboards
  middlewares.py   user context, maintenance, channel lock, throttle
  locales/         fa, en, admin, apps, support, warp catalogues
  handlers/        user, build, panel, apps, extras, warp, support, admin
worker/
  vless-worker.js  the VLESS/WS Worker uploaded to each user's account
```

## Operating notes

- The first sweep starts the moment the bot boots. Give it a minute before the first build.
- The autopilot waits 90 seconds after boot, then works through the queue a few panels at a
  time. Watch it with `docker compose logs -f | grep autopilot`.
- Cloudflare needs up to a minute to publish a brand new `workers.dev` hostname. The bot
  polls the Worker and warns the user instead of handing out a dead config.
- Relay quality drifts. The scanner re-checks the pool every 30 minutes and any relay that
  fails a panel's probe is demoted, so panels built later pick better ones.
- Channel lock requires the bot to be an admin in every channel you add.

## License

MIT. Use it, fork it, ship it.
