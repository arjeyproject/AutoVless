# WARP endpoint engine

How the scanner picks endpoints, how to tune it, and how the list gets pushed to
GitHub on its own.

## Why the rescan button used to lie

Pressing **⚡ Scan endpoints now** almost always answered *"a scan is already
running or just finished"*. Three bugs stacked on top of each other:

1. `scan_once()` returned `0` when the background sweep held its lock, and `0`
   also meant "found nothing", so the handler could not tell the two apart.
2. The per user cooldown was stamped **before** the scan ran, so a scan that
   failed still locked the user out.
3. The sweep was awaited inside the callback, so the button hung for as long as
   the scan took.

Now a sweep already in flight is *joined* instead of refused, every outcome comes
back as its own message (`done`, `joined`, `cooldown`, `empty`, `failed`), and the
scan runs beside the handler and edits its notice when it lands.

## The four passes

1. **Port discovery** — which of the 50+ WARP UDP ports leave this box at all.
2. **Sweep** — one real WireGuard handshake per sampled address on the best three
   ports. Nothing else proves a WARP endpoint is alive: there is no TCP socket,
   and ICMP says nothing about a UDP port.
3. **Verify** — several spaced handshakes per survivor, producing latency,
   jitter and a loss ratio. A miss is data, not a death sentence.
4. **Watchdog** — every couple of minutes the endpoints at the top of the pool
   are re-probed. Three strikes and an address is retired, which is how a
   filtered endpoint disappears in minutes rather than at the next full sweep.

Ranking is `score = latency + jitter x weight + loss x penalty`, smoothed against
the previous score so one lucky handshake cannot promote a flaky address. Lower
is better.

Config builds never wait on any of this. `pick()` reads the pool, and if the pool
is empty it kicks a scan into the background and returns the long lived defaults
immediately.

## Tuning

All optional, all read from `.env`. Defaults suit one small VPS.

| Variable | Default | Meaning |
| --- | --- | --- |
| `WARP_QUICK_SAMPLE` | `3` | addresses per prefix for a user triggered scan |
| `WARP_FULL_GAP` | `240` | minimum seconds between two full sweeps |
| `WARP_QUICK_GAP` | `45` | minimum seconds between two quick sweeps |
| `WARP_USER_COOLDOWN` | `60` | seconds between two presses of the button |
| `WARP_PROBES` | `3` | handshakes per candidate in the verify pass |
| `WARP_PROBE_GAP` | `0.7` | seconds between those handshakes |
| `WARP_PROBE_RETRIES` | `1` | second chances per handshake |
| `WARP_LOSS_MAX` | `0.34` | loss ratio above which an endpoint is not stable |
| `WARP_JITTER_WEIGHT` | `0.7` | cost of 1ms of jitter, in latency ms |
| `WARP_LOSS_PENALTY` | `600` | cost of total loss, in latency ms |
| `WARP_SMOOTHING` | `0.4` | weight of a new measurement against the stored score |
| `WARP_FAIL_LIMIT` | `3` | strikes before an endpoint is retired |
| `WARP_STALE_AFTER` | `21600` | seconds before an unconfirmed row is dropped |
| `WARP_WATCH` | `1` | watchdog on or off |
| `WARP_WATCH_INTERVAL` | `150` | seconds between watchdog passes |
| `WARP_WATCH_SIZE` | `8` | endpoints re-checked per pass |
| `WARP_EXPORT_LIMIT` | `40` | rows written by the exporter |

The existing `WARP_SCAN_*` knobs in `.env.example` still apply: interval, sample,
concurrency, timeout, verify top, pool size, endpoints per config.

Tuning tips from the field:

- Pool keeps coming back empty? Raise `WARP_SCAN_TIMEOUT_MS` to `3500` and
  `WARP_LOSS_MAX` to `0.5`. A congested uplink drops handshakes that a patient
  probe would have caught.
- Endpoints look fast but feel awful? Raise `WARP_JITTER_WEIGHT` to `1.5`.
- Endpoints die within an hour? Drop `WARP_WATCH_INTERVAL` to `90` and
  `WARP_FAIL_LIMIT` to `2` so they are dropped sooner.

## Publishing the list to GitHub

### From the box that runs the bot

```bash
chmod +x scripts/publish_endpoints.sh
GITHUB_TOKEN=ghp_xxx ./scripts/publish_endpoints.sh
```

Then let cron do it:

```cron
*/30 * * * * GITHUB_TOKEN=ghp_xxx /opt/AutoVless/scripts/publish_endpoints.sh >> /var/log/autovless-endpoints.log 2>&1
```

The script takes a `flock`, exports `endpoints/warp-endpoints.{json,txt}`, exits
quietly when nothing changed, rebases before pushing and retries three times. The
token stays in the process: it is never written to `.git/config` and the push
output is swallowed so it cannot leak into a log. A fine grained PAT with
`contents: write` on this repository is enough.

Without `GITHUB_TOKEN` it pushes with whatever credentials the remote already
has, which is what you want if the box uses a deploy key.

### From GitHub Actions

`.github/workflows/warp-endpoints.yml` scans every six hours from the runner's
own network and commits `endpoints/warp-seed.{json,txt}`. Different files from
the VPS output, so the two never conflict. Run it by hand from the Actions tab
with a custom sample size when you want a fresh seed list.

A runner that cannot get UDP out produces an empty list and the job still passes,
by design: a broken seed scan must not turn the repository red.

## Reading the output

```bash
# just the addresses
grep -v '^#' endpoints/warp-endpoints.txt | cut -d' ' -f1

# the healthiest one
python -c "import json;d=json.load(open('endpoints/warp-endpoints.json'));print(d['endpoints'][0]['endpoint'])"
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `⏳ 60s until you can scan again` | per user cooldown | wait, or press it as an admin (admins bypass every gap) |
| `📭 Nothing new answered this round` | the sweep genuinely found nothing | your uplink is blocking WARP ports right now; the old pool is still serving |
| `❌ The scan did not finish` | identity registration failed | Cloudflare rotated its client API or is rate limiting; it retries on the next cycle |
| Pool stuck at 0 stable | every handshake timing out | raise the timeout and `WARP_LOSS_MAX`, and check the box can send UDP to `162.159.192.0/24` |
| `warp_scan` log lines missing | engine disabled | `WARP_ENABLED=1` in `.env`, and the WARP toggle on in the admin options |

Every sweep writes a `warp_scan` event and every watchdog demotion a `warp_watch`
one, both visible in the admin log screen.
