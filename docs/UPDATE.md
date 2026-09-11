# Running and updating the bot

Everything here assumes the repo is cloned on the server and the bot runs under
systemd. If you use Docker instead, jump to the bottom.

## The one step people forget

Updating the bot does **not** update anybody's worker. A panel that is already
live keeps running the bundle it was uploaded with, so a new protocol - Trojan,
for instance - stays silent until that bundle is replaced. That happens when a
panel is re-uploaded:

- the user presses **apply clean IPs** or **rebuild panel**, or
- the autopilot reaches that panel on its next cycle, or
- an admin presses **apply on every panel** in the scan engine screen.

So after an update: restart the bot, then press *apply on every panel* once.

## First install

```bash
git clone https://github.com/arjeyproject/AutoVless.git /opt/autovless
cd /opt/autovless
bash install.sh          # venv, requirements, .env, systemd unit
nano .env                # BOT_TOKEN and ADMIN_IDS at minimum
sudo systemctl enable --now autovless
```

## Update to the newest version

```bash
cd /opt/autovless
sudo systemctl stop autovless

# keep the database out of it
cp -a data/autovless.db "data/autovless.db.$(date +%F-%H%M).bak"

git fetch --all
git reset --hard origin/main          # local edits are discarded, on purpose
source .venv/bin/activate
pip install -r requirements.txt --upgrade

# syntax gate. If this prints a failure, do not restart yet.
bash scripts/syntax-check.sh

sudo systemctl start autovless
sudo systemctl status autovless --no-pager
```

Then watch it come up:

```bash
journalctl -u autovless -f -n 100
```

A healthy start logs the scanner, the curator and the autopilot booting, and
nothing at `ERROR`.

## Push the new worker to every panel

As an admin in the bot: **my panel -> apply clean IPs** for your own panel, or
**admin panel -> scan engine -> apply on every panel** for all of them. Either
way the subscription links never change; only what sits behind them does.

To confirm a panel is on the new bundle, open:

```
https://<your-host>.workers.dev/<uuid>/health
```

and look for `"protocols": ["vless", "trojan"]`. A panel still on the old bundle
omits that field entirely, which is the fastest way to tell them apart.

## Verify Trojan actually works

```bash
# the trojan-only subscription, base64
curl -s https://<host>/<uuid>/trojan | base64 -d | head

# both protocols in one subscription
curl -s https://<host>/<uuid>/mix | base64 -d | head

# can the worker open outbound sockets at all
curl -s https://<host>/<uuid>/probe
```

The Trojan password is the panel UUID, and the **Trojan configs** button prints
it next to the links. Trojan is offered on TLS ports only: on a plain port there
is no TLS record for the handshake to hide inside, so the password would cross
the wire in the clear and clients refuse it.

To turn Trojan off for a panel, bind `TROJAN=false` on the worker; to use a
password that is not the UUID, bind `TROJAN_PASSWORD`.

## Roll back

```bash
cd /opt/autovless
git log --oneline -n 10
sudo systemctl stop autovless
git reset --hard <commit>
sudo systemctl start autovless
```

The worker rolls back the same way it rolled forward: reset the code, then press
apply so the older bundle is re-uploaded.

## Docker

```bash
cd /opt/autovless
git pull
docker compose build --pull
docker compose up -d
docker compose logs -f --tail 100
```

## Quick health checklist

```bash
systemctl is-active autovless                                  # active
journalctl -u autovless --since '10 min ago' | grep -i error   # empty
ls -l data/autovless.db                                        # exists, recent
```

In the bot, **live network status** should show a verified pool above zero and a
best ping under a second. If the pool is empty, press *scan IPs now* and give it
a minute; if it stays empty, the box's own network is the suspect, not the bot.
