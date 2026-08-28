# Why port 443 configs did not ping, and what now stops it

## The symptom

A panel shipped three plain configs on port 80, all of which pinged, and five TLS
configs on port 443, none of which did. Consistently, on every rebuild.

## The cause

The two groups were never held to the same standard.

Every candidate address used to be verified with `GET /cdn-cgi/trace` for the
hostname `cloudflare.com`. On a plain HTTP port that is almost exactly what a
client sends: same plaintext request, same Host-header routing, same edge
behaviour. Port 80 was therefore verifying the thing it was about to ship.

On a TLS port it is a different conversation: a different SNI, a different
certificate, a different origin. Cloudflare answers `cloudflare.com` from any
edge address whether or not that address will complete a TLS session for *your*
`*.workers.dev` hostname on *that* port and upgrade a WebSocket on it. So port
 443 was verifying something no client would ever ask for.

Two smaller faults turned a weak check into a guaranteed failure:

- `collect_endpoints()` topped up short groups with `verified_only=False` rows, so
  a thin TLS pool did not produce fewer configs, it produced five untested ones.
- The worker pinned every config in a group to `ports[0]`, so the whole TLS set
  sat on 443. One filtered port took out all five at once.

## The fix

1. **Probes speak the client's sentence** (`bot/probe.py`). TCP, then TLS with the
   panel's own SNI, then `GET /?ed=2560` with `Upgrade: websocket`. Nothing is
   verified without `101 Switching Protocols`. The trace check survives only to
   warm a pool that has no panel to aim at yet, and never as a fallback from a
   failed handshake.
2. **An acceptance gate at deploy time** (`bot/deploy.py`). After the worker is
   live, every endpoint about to ship must complete that handshake against this
   panel's hostname, on its own port and path. Failures are demoted in the pool,
   replaced from the pool, and the worker is re-uploaded with the healed list. If
   the pool has nothing that works, the panel ships short on purpose: four
   configs that ping beat nine that do not.
3. **Verified rows only, spread across ports** (`bot/vless.py`). No unverified
   endpoint reaches a user, groups are filled round-robin across all their ports,
   and slots a group cannot fill honestly move to a group that can.
4. **Defaults widened**: `TLS_PORTS=443,2053,8443`, `HTTP_PORTS=80,8080`. A single
   filtered port can no longer empty a group. Alternate TLS ports are labelled in
   the config name so a user can see which one they are on.

## Deploying

```bash
cd /opt/autovless
git pull
docker compose up -d --build
docker compose logs -f --tail=100
```

What to look for in the log:

```
port 443 wave 1: 128 reachable, 31 verified via ws
selected 9 endpoints (...)
rejected 104.x.x.x:443 for <panel>.workers.dev, no websocket upgrade
panel built host=... endpoints=9 rejected=0 healthy=True
```

`verified via trace` on the first run is expected: no panel exists yet to verify
against. Build one panel and every sweep after that verifies with `ws`. To pin it
yourself, set `VERIFY_HOST=yourpanel.yoursub.workers.dev` in `.env`.

## Scheduled scanning

`.github/workflows/clean-ips.yml` sweeps every three hours from GitHub's network
and commits `endpoints/clean-ips.{txt,json}`. The bot reads that file as a local
seed (`CLEAN_IP_FILES`), so it works the same on a private repository. Set the
`VERIFY_HOST` repository variable to a live panel hostname and the scheduled scan
uses the same real upgrade check.
