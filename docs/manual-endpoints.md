# Filling the WARP pools by hand

## Why the feature exists

Two pools, one per address family, and the mapping is the product:

| user button | pool | why |
| --- | --- | --- |
| 📶 Irancell | **IPv6** | MTN shapes and drops WARP over IPv4 and mostly leaves its IPv6 path alone |
| 🌐 Other operators | **IPv4** | every other Iranian operator is the other way round |

The scanner fills both pools by itself, and on one very common box it cannot fill
the IPv6 one at all: Cloudflare's IPv6 WARP prefixes are reachable from an
Irancell handset and *not* from most Iranian VPS hosts. `warpep.reachable()`
reports that honestly (a red mark next to IPv6 on the pool screen), which is much
better than the fake zero it used to print, but the Irancell pool is still empty.

Meanwhile the admin is holding a list of IPv6 endpoints that demonstrably work on
the phone in their hand. That list is what these buttons are for.

## Where it lives

```
Admin panel  ->  Endpoint pools
                 |- Refresh pools          (scan both)
                 |- Refresh IPv4 / IPv6    (scan one family)
                 |- Add IPv4 by hand       <- new
                 |- Add IPv6 by hand       <- new
                 |- Hand entered endpoints <- new
                 |- Full endpoint check
                 `- Pool listing
```

One button per family, never a combined one. "Which pool" *is* "which operator",
so it is a decision the admin makes explicitly rather than one inferred from the
address that was pasted. An IPv6 literal sent to the IPv4 button is reported as
`wrong family` and not helpfully filed elsewhere.

## What you can paste

One endpoint per line, or several separated by spaces, commas, semicolons, pipes
or Persian commas. Bullets, arrows, quotes, direction marks and Persian digits
are all stripped, because the real input is a paste out of a channel.

```
162.159.192.1:2408
188.114.98.10                     <- no port means 2408
[2606:4700:d0::a29f:c001]:2408
[2606:4700:d1::a29f:c101]         <- brackets, no port
۱۸۸.۱۱۴.۹۶.۱:۲۴۰۸                  <- Persian digits are fine
```

**Always bracket an IPv6 address when you want to give it a port.** Nothing can
tell `2606:4700:d0::a29f:c001:2408` apart from a plain address, so an unbracketed
IPv6 literal is read as an address on port 2408 and never as a port.

Up to `WARP_MANUAL_MAX` (40) endpoints per paste.

## What happens to each line

Every accepted address gets exactly what a scanned one gets: several spaced,
cryptographically verified WireGuard handshakes, latency, jitter and loss, then
WarpEP's 0-100 health score against `WARP_HEALTH_FLOOR`.

| verdict | meaning |
| --- | --- |
| `stored` | answered, cleared the floor, in the pool and being handed out |
| `untested` | this host has no route for that family, stored on trust |
| `dead` | never answered a handshake, **not** stored |
| `weak` | answered but below the floor or too lossy, **not** stored |
| `family` | that is an address of the other family |
| `dup` | the same endpoint twice in one paste |
| `bad` | not an IP address |
| `over` | past the per paste cap |

So the pool guarantee is unchanged: **only healthy endpoints reach users.** Hand
entry is a new way in, not a way around the floor.

## Untested rows, and why they are allowed

When the host has no route for the family there is no handshake to be had. The
choice is between storing the address untested and refusing the one feature that
exists for this exact situation, so it is stored with:

* `latency = 0` - the screen shows `-`, because there is no measurement to show,
* `verified = -1` - not checked, which is different from checked and failed,
* a deliberately terrible ranking score.

Every pool read sorts untested rows **last**, so a measured endpoint always goes
out first and an untested one is only handed out when it is all there is. The
report and the manual screen both say so in words.

## Pinned means pinned

A manual row carries `manual = 1` in `warp_endpoints`, and that changes three
things in `bot/warpstore.py` and nothing else:

* `trim`, `retire` and `purge_unhealthy` skip it. The scanner's cap deleting the
  list an admin entered ten minutes ago is indistinguishable from the feature
  being broken.
* `drop` *sidelines* it (`stable = 0`, `health = 0`) instead of deleting it, so a
  pinned endpoint that dies is still on the manual screen, marked dead.
* It can be stored untested, as above.

What it does **not** get is a pass on health. `warpstore.pool()` filters manual
rows through the same floor as everything else, so a dead pinned endpoint is
never handed to a user - it just stays visible to the admin who pinned it. The
agent re-probes everything stored on every pass, so a sidelined manual endpoint
revives by itself the moment it answers again. `Re-check the pinned ones` does
that immediately for the hand entered list only, which is a lot cheaper than the
full audit.

## Clearing

`Clear manual IPv4` / `IPv6` asks for confirmation and then deletes that family's
pinned endpoints only. Scanned rows are untouched.

## Knobs

| variable | default | what it does |
| --- | --- | --- |
| `WARP_MANUAL_PROBES` | 3 | spaced handshakes per pasted endpoint |
| `WARP_MANUAL_MAX` | 40 | endpoints accepted from a single paste |
| `WARP_HEALTH_FLOOR` | 55 | minimum health, shared with the scanner |

## Deploying

```bash
cd /opt/autovless            # wherever the repo lives
git pull
docker compose up -d --build
docker compose logs -f --tail=100
```

The `manual` column is added in place by `warpstore.ensure_schema()` on the first
run. Nothing to migrate, nothing to drop, and an existing warm pool keeps
working.

What to look for in the log after pinning a list:

```
warp pool: column manual added
warp pool: 6 manual endpoint(s) pinned (measured)
manual v6 import: 6 stored, 0 untested, 2 dead, 1 weak, pool now 6
```

Or, on a host without IPv6:

```
warp pool: 6 manual endpoint(s) pinned (untested, no route here)
```
