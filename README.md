# AutoVless

A Telegram bot that builds a private VLESS panel **on each user's own Cloudflare account**.
The user pastes an API token, the bot scans for clean Cloudflare edge IPs, deploys a Worker,
and hands back six working configs: three on port 443 (TLS) and three on port 80.

Built so people in Iran can reach an open internet. Free, no subscriptions, no resellers.

ربات تلگرامی که روی اکانت کلادفلر خود کاربر یک پنل VLESS می‌سازد، آی‌پی تمیز اسکن می‌کند
و شش کانفیگ سالم (سه تا پورت ۴۴۳ و سه تا پورت ۸۰) تحویل می‌دهد.

---

## What it does

- **Glass panel UI**: every screen is an inline keyboard, fully bilingual (فارسی / English)
- **Two-step Cloudflare onboarding**: sign-up button, then a token button with the exact
  permissions pre-selected (Workers Scripts edit, Account read, Zone read, DNS edit)
- **Clean IP scanner**: continuous background sweep of Cloudflare's published prefixes,
  verified with a real HTTP request that also reveals the edge colo
- **Automatic Worker deploy**: uploads a VLESS-over-WebSocket Worker to the user's account,
  enables `workers.dev`, and mounts the fastest clean IPs onto the configs
- **Subscription served by the Worker itself**: base64, Clash / Mihomo, and sing-box endpoints
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
| `PROXY_IP` | empty | Optional relay for destinations Cloudflare cannot reach |
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
           the user's own Worker  ──►  destination
```

The address field carries a clean IP, while `Host` and `sni` carry the Worker hostname.
That is why swapping in a faster IP never breaks the config: only the entry point changes.

## Project layout

```
bot/
  main.py          entrypoint and dispatcher wiring
  config.py        environment-driven settings
  db.py            SQLite storage, encrypted token vault
  cloudflare.py    Cloudflare API client
  scanner.py       clean IP scanner
  deploy.py        token to live Worker
  vless.py         links, Clash, sing-box
  warp.py          WARP / WireGuard provisioning
  screens.py       shared screen composition
  keyboards.py     inline keyboards
  middlewares.py   user context, maintenance, channel lock, throttle
  locales/         fa, en, admin catalogues
  handlers/        user, build, panel, extras, admin
worker/
  vless-worker.js  the Worker uploaded to each user's account
```

## Operating notes

- The first sweep starts the moment the bot boots. Give it a minute before the first build.
- Cloudflare needs up to a minute to publish a brand new `workers.dev` hostname. The bot
  health-checks the Worker and warns the user instead of handing out a dead config.
- Channel lock requires the bot to be an admin in every channel you add.
- `docker compose logs -f` is the fastest way to see what the scanner is finding.

## License

MIT. Use it, fork it, ship it.
