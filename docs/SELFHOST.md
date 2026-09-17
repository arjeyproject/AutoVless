# Self-hosting: why, and how

## Why the Cloudflare suspensions are not a bug

Users report that their Cloudflare account is suspended about two days after
setting a panel up, and that every config dies with it. Nothing in this
repository causes that, and no change to this repository stops it.

Cloudflare's Self-Serve Subscription Agreement, updated on 3 December 2024,
lists what you may not do with the Services. Two of those clauses describe
exactly what a Workers-based VLESS panel does:

> (j) use the Services to provide a virtual private network or other similar
> proxy services.

> (b) interfere with, disrupt, alter, or modify the Services [...] including,
> but not limited to, causing (whether directly or indirectly) traffic for your
> Cloudflare-proxied domain to be sent to an IP address that was not assigned by
> Cloudflare for the domain.

Clause (j) covers the proxy itself. Clause (b) covers clean-IP selection - the
whole point of the scanner. Section 8 lets Cloudflare suspend or terminate an
account for a breach of 2.2, with or without notice. What users are seeing is
enforcement, on schedule, of a rule that was written down in advance.

A panel can be quieter about it and buy time. Every one of them, this project
included, is still one detection pass away from the same suspension, and the
account that gets closed belongs to the user, not to you. That is not a
foundation to put your users' service on.

## What replaces it

One `sing-box` process on a VPS you rent, serving two inbounds on your own IP:

| | VLESS + REALITY | Shadowsocks-2022 |
|---|---|---|
| Port | 443/tcp | 8443/tcp+udp |
| Needs a domain | no | no |
| Needs a certificate | no | no |
| Third-party account | none | none |
| Cipher / handshake | real borrowed TLS 1.3 + Vision | `2022-blake3-aes-128-gcm` |

REALITY does not present a certificate of its own. It completes a genuine TLS
1.3 handshake with a real, unrelated site and hands the session over only for
clients that prove they hold the key, so there is no certificate to fingerprint
and no domain of yours anywhere in the exchange. This is what the Xray-based
panels run, and it is the most durable shape available today.

Shadowsocks-2022 is the current revision of the protocol: session-based, with
BLAKE3-derived subkeys and replay protection in the specification rather than
bolted on. It needs no plugin, no TLS wrapper and no WebSocket, so a user can be
handed a working config with zero server-side work - which is what makes the free
tier free and automatic. It supersedes the AEAD-over-WebSocket build in
`bot/shadowsocks.py`, which stays for the Worker path.

Nothing about this removes the Cloudflare panel flow. Both can run side by side;
this is the path that does not depend on somebody else's terms of service.

## Install

On the VPS, as root:

```bash
cd /opt/autovless          # wherever the bot lives
git fetch origin
git checkout fix/stability-and-selfhost
sudo -E bash scripts/install-selfhost.sh
```

It installs sing-box from the official Sagernet repository, generates the REALITY
keypair, short id, uuid and Shadowsocks pre-shared key, writes
`/etc/sing-box/config.json`, validates it with `sing-box check`, enables BBR,
raises the file-descriptor limit, opens the ports in `ufw` if you use it, starts
the service, and prints a block like this:

```
SELFHOST=1
SELFHOST_HOST=203.0.113.10
REALITY_PORT=443
REALITY_SNI=www.datadoghq.com
REALITY_PBK=...
REALITY_SID=...
REALITY_UUID=...
SS2022_PORT=8443
SS2022_METHOD=2022-blake3-aes-128-gcm
SS2022_PSK=...
SELFHOST_PER_USER=0
```

Append it to the bot's `.env` and restart the bot:

```bash
sudo -E bash scripts/install-selfhost.sh >> /opt/autovless/.env   # or paste it
sudo systemctl restart autovless        # or: docker compose up -d --build
```

Then `/selfhost` in the bot hands any user a REALITY link, a Shadowsocks-2022
link, a base64 subscription, and sing-box or Clash exports.

The script is idempotent. Running it again re-prints the existing block instead
of rotating keys, because rotating them would kill every config your users have
already saved. `FORCE=1` rebuilds from scratch.

## Per-user credentials

The free tier shares one server key on purpose: a new user costs no provisioning
steps. When you want credentials you can revoke individually:

```bash
sudo python3 scripts/selfhost-user.py add 123456789
sudo python3 scripts/selfhost-user.py list
sudo python3 scripts/selfhost-user.py remove 123456789
```

Then set `SELFHOST_PER_USER=1` in `.env` and restart the bot. Both halves derive
the same values by HMAC from the bot's `SECRET_KEY`, so the node and the bot
never need to exchange anything. Do not turn that flag on before registering
people, or the bot will hand out credentials the server has never seen.

## Checks

```bash
systemctl status sing-box --no-pager
journalctl -u sing-box -n 50 --no-pager
sing-box check -c /etc/sing-box/config.json
ss -tulpn | grep sing-box
```

If REALITY will not connect, the SNI is the first thing to look at: it must be a
real host that speaks TLS 1.3 with HTTP/2, must not be behind Cloudflare, and
should be somewhere your users can plausibly reach. `www.datadoghq.com`,
`www.lovelive-anime.jp` and `www.swift.com` are the usual choices. Change it with
`SNI=... FORCE=1` and re-run.

Keep `/etc/autovless/selfhost.env`. It is the only copy of the keys.
