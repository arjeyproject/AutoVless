# WARP endpoint pools: how they fill, and why they were not filling

## The symptom

```
✅ IPv6 pool refreshed
🔍 Addresses swept: 48
📞 Answered: 0
❤️ Judged healthy: 0
🏊 Pool: 0/10
🔌 Ports: 2408 · 500 · 1701
⏱ Took: 4s
```

Every number in there is a clue and the old report wasted all of them.

* **48 addresses** is `WARP_POOL_SAMPLE` (24) times the two IPv6 prefixes, so this
  was the IPv6 sweep.
* **4 seconds** for 144 handshakes is far too fast to be timeouts. Those probes
  were not timing out, they were failing *instantly*: `ENETUNREACH`.
* **Ports 2408 / 500 / 1701** is exactly `PRIMARY_PORTS[:3]`, the hardcoded
  fallback. Port discovery had found nothing either.

Three independent bugs produced that screen.

## 1. The container had no IPv6

Docker's default bridge network is IPv4-only. Nothing in the scanner checked, so
every IPv6 probe failed at `connect()` and was counted as a dead endpoint.

Fixed by `network_mode: host` in `docker-compose.yml`, plus `warpep.reachable()`,
which asks the kernel for a route before a sweep starts and reports
`unreachable` instead of a fake zero.

Check it from inside the container:

```bash
docker compose exec autovless python - <<'PY'
import socket
for af, host in ((socket.AF_INET, "162.159.192.1"), (socket.AF_INET6, "2606:4700:d0::a29f:c001")):
    s = socket.socket(af, socket.SOCK_DGRAM)
    try:
        s.connect((host, 2408)); print(host, "route OK")
    except OSError as e:
        print(host, "NO ROUTE:", e)
    finally:
        s.close()
PY
```

If the IPv6 line says `NO ROUTE`, the host itself has no IPv6 and no code change
will produce an IPv6 pool. Fix the server, or accept an IPv4-only pool: the bot
now says so plainly instead of pretending to scan.

## 2. The probing identity was never validated

This is the important one, and WarpEP's `warpep/identity.py` documents it at
length: Cloudflare's WARP responder checks `mac1`, then decrypts the initiation
to learn *which client* is calling, and looks that public key up in its peer
list. **If the key is not an enrolled WARP device the packet is dropped in
silence.** No response, no ICMP error, nothing.

So a scan signed with a key Cloudflare does not know does not look slow. It looks
like every endpoint on earth is dead.

AutoVless registered a device once, cached it in the database and trusted it
forever. When Cloudflare dropped that device - or when registration failed
because `api.cloudflareclient.com` is blocked from the server, which on an
Iranian VPS it usually is - every sweep from then on reported zero.

`warpscan.identity()` now:

1. preflights the cached identity against Cloudflare's own published control
   endpoints and throws it away if nothing answers,
2. re-registers, and preflights that too,
3. falls back to WarpEP's enrolled probing identity, which needs no network call
   at all.

The pool screen prints which identity is in use and whether Cloudflare answers
it.

## 3. The panel scan only ever swept IPv4

`warp_scanner.scan()` defaulted to `family=V4`, so the admin rescan button could
not put a single address into the IPv6 pool however long you waited. `family=None`
now means "every family this host can reach".

Related: the legacy sweep capped the whole table with a family-blind trim, so a
busy IPv4 pool could evict every IPv6 row that had just been found. It trims per
family now.

## Deploying

```bash
cd /opt/AutoVless           # wherever the repo lives
git pull
docker compose build --no-cache
docker compose up -d
docker compose logs -f --tail=100 autovless
```

What to look for in the log, in this order:

```
scanner identity: warpep bundled ...      # or "registered (free)"
warp ports reachable over v4: [2408, ...]
warp ports reachable over v6: [2408, ...]
pool v4 refreshed: 31 answered, 12 healthy, 10 stored, pool 10/10 (ok)
pool v6 refreshed: 18 answered, 9 healthy, 9 stored, pool 9/10 (ok)
```

If you see `no usable IPv6 route`, go back to section 1. If you see `neither a
registered device nor the bundled WarpEP identity gets an answer`, outbound UDP
is blocked on the box: check the firewall for UDP 2408, 500, 1701 and 4500.

## Knobs worth knowing

| variable | default | what it does |
| --- | --- | --- |
| `WARP_POOL_TARGET` | 10 | healthy endpoints kept per family |
| `WARP_POOL_SAMPLE` | 24 | addresses per prefix on a refresh |
| `WARP_HEALTH_FLOOR` | 55 | minimum WarpEP health to enter a pool |
| `WARP_DEEP_VERIFY` | on | prove endpoints carry traffic, needs `warpep` |
| `WARP_AGENT_INTERVAL` | 300 | seconds between agent passes |
| `WARP_SCAN_TIMEOUT_MS` | 2500 | per-handshake timeout |

Raise `WARP_POOL_SAMPLE` before lowering `WARP_HEALTH_FLOOR`. A wider sweep finds
better endpoints; a lower floor just admits worse ones.
