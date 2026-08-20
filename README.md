# AutoVless

A Telegram bot that builds a private VLESS panel **on each user's own Cloudflare account**.
The user pastes an API token, the bot scans for clean Cloudflare edge IPs and working
proxyIP relays, deploys a Worker, verifies the tunnel actually carries traffic, and hands
back six configs: three on port 443 (TLS) and three on port 80.

Built so people in Iran can reach an open internet. Free, no subscriptions, no resellers.

ربات تلگرامی که روی اکانت کلادفلر خود کاربر یک پنل VLESS می‌سازد، آی‌پی تمیز و پروکسی‌آی‌پی سالم
اسکن می‌کند و شش کانفیگ سالم (سه تا پورت ۴۴۳ و سه تا پورت ۸۰) تحویل می‌دهد.

---

## What it does

- **Glass panel UI**: every screen is an inline keyboard, fully bilingual (فارسی / English)
- **Two-step Cloudflare onboarding**: sign-up button, then a token button with the exact
  permissions pre-selected (Workers Scripts edit, Account read, Zone read, DNS edit)
- **Clean IP scanner**: curated public lists mixed into a continuous random sweep of
  Cloudflare's prefixes, each candidate verified with a real `/cdn-cgi/trace` request that
  also reveals the edge colo
- **proxyIP scanner**: finds relays that forward TCP to the Cloudflare edge, rejects anything
  resolving into a Cloudflare prefix (a Worker cannot dial those), and keeps a self-healing
  pool. Every panel ships with an ordered failover chain of relays
- **Automatic Worker deploy**: uploads a real VLESS-over-WebSocket Worker to the user's
  account, enables `workers.dev`, mounts the fastest clean IPs onto the configs
- **Health gate**: a panel is only reported as ready after `/health` answers *and* the
  Worker proves it can open an outbound socket. Dead relays are demoted automatically
- **Subscription served by the Worker itself**: base64, raw, Clash / Mihomo, sing-box
- **Panel management**: QR code, subscription links, individual configs, live ping test,
  rescan, rebuild, delete
- **WARP / WireGuard generator** and a **vless link converter**
- **Advanced admin panel**: stats, user search with ban controls, broadcast, forced-channel
  lock, scan engine controls, feature toggles, event log, database backup

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

Upgrading an existing install:

```bash
cd /opt/autovless
git pull
docker compose up -d --build
```

Existing panels keep working, but they were deployed with the old Worker. Have users hit
**Rebuild panel** once so the new Worker is pushed to their account.

Full step-by-step guide with troubleshooting: [`docs/install.html`](docs/install.html).

## Configuration

Everything lives in `.env`. The two required values are `BOT_TOKEN` and `ADMIN_IDS`.

| Key | Default | Meaning |
| --- | --- | --- |
| `BRAND` | `AutoVless` | Name used in config remarks and messages |
| `DEFAULT_LANG` | `fa` | `fa` or `en` |
| `TLS_CONFIG_COUNT` / `HTTP_CONFIG_COUNT` | `3` / `3` | Configs per panel |
| `TLS_PORTS` / `HTTP_PORTS` | `443` / `80` | Cloudflare edge ports to use |
| `SCAN_INTERVAL` | `600` | Seconds between background sweeps |
| `SCAN_BATCH` | `1200` | Addresses probed per port per sweep |
| `SCAN_CONCURRENCY` | `160` | Parallel sockets. Raise only on bigger boxes |
| `POOL_SIZE` | `120` | Endpoints kept in the pool |
| `CLEAN_IP_SOURCES` | IPDB best CF list | Curated edge lists mixed into every sweep |
| `PROXY_IP` | built-in seeds | Pin your own relays, e.g. `1.2.3.4:443,relay.example.com` |
| `PROXY_IP_SOURCES` | IPDB best proxy list | Public relay lists to scan |
| `PROXY_SCAN_INTERVAL` | `1800` | Seconds between relay sweeps |
| `PROXY_POOL_SIZE` | `40` | Relays kept in the pool |
| `PROXY_PER_PANEL` | `3` | Relays baked into each panel as a failover chain |
| `DNS_SERVER` | `8.8.8.8` | Resolver the Worker uses for UDP/53 |
| `HEALTH_ATTEMPTS` | `6` | Polls of a fresh `workers.dev` hostname before giving up |
| `STORE_TOKENS` | `true` | Keep tokens encrypted so rebuild and delete work |

Tokens are encrypted with a key derived from `SECRET_KEY`. If you leave `SECRET_KEY` empty,
one is generated on first run and stored in `data/.secret`.

## How the config chain works

```
client  ──►  clean Cloudflare IP : 443 or 80
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

The address field carries a clean IP, while `Host` and `sni` carry the Worker hostname.
That is why swapping in a faster IP never breaks the config: only the entry point changes.

The Worker tries the destination directly first. If the handshake fails, or the socket
returns nothing at all, it walks the relay chain in order. That second path is not
optional: Cloudflare blocks Worker sockets to its own addresses, so without a live relay
every Cloudflare-fronted site looks dead and the client reports `-1ms`.

## Worker endpoints

Everything is namespaced under the panel UUID, so nothing is guessable.

| Path | Returns |
| --- | --- |
| `/<uuid>` | base64 subscription |
| `/<uuid>/raw` | plain `vless://` links |
| `/<uuid>/clash` | Clash / Mihomo YAML |
| `/<uuid>/singbox` | sing-box JSON |
| `/<uuid>/health` | build stamp, endpoint and relay counts, serving colo |
| `/<uuid>/probe` | live outbound socket test, per relay |

`?proxyip=host:port` on the WebSocket URL overrides the relay chain for one session, which
is the fastest way to test a relay by hand.

## Troubleshooting configs that show `-1ms`

1. Open `https://<host>/<uuid>/probe`. If `ok` is false, the Worker cannot open sockets at
   all: the account is brand new or the script was uploaded without the runtime bindings.
   Rebuild the panel.
2. If `usable_relays` is `0`, every relay in the chain is dead. Run a relay sweep from the
   admin panel, or pin a known good one in `PROXY_IP` and rebuild.
3. If the probe is healthy but the client still fails, the entry IP is blocked on that
   network. Use **Rescan clean IPs**, then **Rebuild panel**, and try the port 80 configs.
4. On mobile data, port 80 usually behaves better; on fixed lines, 443 usually wins.

## Project layout

```
bot/
  main.py          entrypoint and dispatcher wiring
  config.py        environment-driven settings
  db.py            SQLite storage, encrypted token vault
  proxies.py       proxyIP relay pool
  cloudflare.py    Cloudflare API client
  scanner.py       clean IP and proxyIP scanners
  deploy.py        token to live, health-checked Worker
  vless.py         links, Clash, sing-box
  warp.py          WARP / WireGuard provisioning
  screens.py       shared screen composition
  keyboards.py     inline keyboards
  middlewares.py   user context, maintenance, channel lock, throttle
  locales/         fa, en, admin catalogues
  handlers/        user, build, panel, extras, admin
worker/
  vless-worker.js  the VLESS/WS Worker uploaded to each user's account
```

## Operating notes

- The first sweep starts the moment the bot boots. Give it a minute before the first build.
- Cloudflare needs up to a minute to publish a brand new `workers.dev` hostname. The bot
  polls the Worker and warns the user instead of handing out a dead config.
- Relay quality drifts. The scanner re-checks the pool every 30 minutes and any relay that
  fails a panel's probe is demoted, so panels built later pick better ones.
- Channel lock requires the bot to be an admin in every channel you add.
- `docker compose logs -f` is the fastest way to see what the scanners are finding.

## License

MIT. Use it, fork it, ship it.
