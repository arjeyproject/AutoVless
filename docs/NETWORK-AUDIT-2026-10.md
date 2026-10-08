# AutoVless network resilience audit

Audit date: 2026-10-08
Repository: `arjeyproject/AutoVless`
Branch audited: `main`

## Scope

The audit followed the existing data flow from Telegram bot and Mini App through the API, SQLite pool, Cloudflare Worker deployment, subscription rendering, and WARP/WireGuard endpoint selection. The existing bot, menus, Mini App, database shape, deployment flow, and Worker were treated as the system of record.

## Findings

### Root cause of misleading client latency

`bot/api.py` currently implements `/api/panel/ping` with `tcp_latency()`. That only measures a socket connect to `ip:port`; it does not use the panel hostname as SNI, perform the configured TLS handshake, send the configured WebSocket upgrade, validate HTTP status `101`, or validate the selected transport. The Mini App can therefore show a green number for an endpoint that the generated VLESS/Trojan configuration cannot use.

The deploy acceptance path in `bot/deploy.py` is stronger: it uses `bot/probe.py`, the panel host, the configured WebSocket path, and requires `101`. The API and Mini App do not use that same source of truth.

### Unverified endpoints can re-enter subscriptions

The bot-side generator selects verified rows, but `worker/vless-worker.js` dynamically blends `CLEAN_DOMAINS` and fetched `SUB_SOURCES` into live subscriptions. Those entries are not proven against the user's actual panel path before being emitted. This violates the requirement that a dead or untested endpoint must not be presented as healthy.

### Health and endpoint state are split

The panel payload exposes stored endpoint rows, while the Worker can independently rotate additional rows. This creates two views of reality: the Bot/Mini App view and the Worker subscription view. They can disagree after a health change or source refresh.

### Worker health is not the same as endpoint health

The Worker `/health` and `/probe` checks prove Worker publication and outbound reachability. They do not prove every client entry address can complete the panel's TLS/WebSocket handshake. Both checks are needed and must not be conflated.

### WARP/WireGuard is a separate path

`bot/wireguard.py` performs a real WireGuard initiation/response check, which is the correct class of test for a UDP endpoint. It must remain separate from the HTTP/WebSocket clean-IP pool. ICMP or TCP checks are not substitutes for a WireGuard handshake.

## Existing strengths preserved

- The repository already has a real WebSocket probe requiring HTTP `101`.
- TLS probes use the panel hostname as SNI and disable certificate validation only for reachability measurement.
- Endpoint selection drops unverified rows and spreads selection across configured ports.
- Curator rechecks stored endpoints and can remove failed rows and refresh affected panels.
- Trojan and Shadowsocks are restricted to TLS endpoints.
- WARP has a genuine WireGuard handshake probe.
- Mini App API authorization is tied to Telegram WebApp signed `initData` and job ownership.
- Secrets are intended to remain in environment/database encryption rather than Git.

## Required implementation order

1. Make `/api/panel/ping` call the same `probe.measure()` client-path check used by deployment, and return `healthy`, `latency`, `jitter`, `method`, and an explicit failure reason. Never return a latency value when the client-path probe fails.
2. Make one endpoint-selection function the source of truth for Bot, Mini App, direct subscriptions, and Worker bindings. Do not ship dynamically fetched source rows unless they have passed the panel-path probe.
3. Add endpoint family metadata and operator/profile dimensions without hard-coding an operator guess. Keep IPv4 and IPv6 selection independent.
4. Add panel schema fields for worker health timestamps and Worker diagnostics using additive migrations only. Do not silently discard Worker status updates.
5. Add protocol validation for VLESS, Trojan, Shadowsocks, and WireGuard before rendering or subscription refresh.
6. Add integration tests that exercise DNS, TCP, TLS/SNI, WebSocket `101`, Worker `/health`, Worker `/probe`, subscription filtering, and Telegram user isolation.

## Verification status

This audit was source-based. No Cloudflare account, Telegram client, real endpoint pool, or production Docker host was available to execute live protocol tests from this audit context. Live VLESS, Trojan, Shadowsocks, WireGuard, Worker, subscription, and Mini App checks therefore remain **NOT TESTED**.

## Git state observed

- Default branch: `main`
- Repository owner: `arjeyproject`
- Repository: `AutoVless`
- Existing resilience-related branches were present, including `iran-resilience`, `fix/audit`, and `feature/clean-ip-curator`.
- No secret values were copied into this document.
