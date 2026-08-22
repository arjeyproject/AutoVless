# Published WARP endpoints

Machine readable output of the endpoint engine. Nothing in here is edited by
hand: both files in a pair are rewritten in full every time.

| File | Written by | Measured from |
| --- | --- | --- |
| `warp-endpoints.json` / `.txt` | `scripts/publish_endpoints.sh` on the bot host | your server's network |
| `warp-seed.json` / `.txt` | `.github/workflows/warp-endpoints.yml` | a GitHub runner |

The `.txt` files are one `ip:port` per line with the measurement in a trailing
comment, so they can be piped straight into other tooling:

```bash
grep -v '^#' endpoints/warp-endpoints.txt | cut -d' ' -f1
```

The `.json` files carry the full record per endpoint: latency, jitter, loss ratio
and the combined score the bot ranks by. Lower score is better.

Endpoint health is relative to the network you measure from. Trust
`warp-endpoints.*` for your own users and treat `warp-seed.*` as a warm start for
a fresh deployment.
