# Cloudflare Pages subscription gateway

The tunnel remains on the user's Worker because `cloudflare:sockets` and the WebSocket tunnel runtime belong there. Pages is used as the public, free front door for `/sub/*` and `/dl/*`, so clients never need to resolve `workers.dev` to refresh a profile or download a WireGuard file.

## Pages setup

1. Create a Pages project from this repository.
2. Set the output directory to `webapp` and leave the build command empty.
3. Add the Pages environment variable `AUTOVLESS_ORIGIN=https://your-vps-domain.example`.
4. Put the Pages custom domain in the VPS `.env` as `PUBLIC_URL=https://pages-your-domain.example`.
5. Keep `WEBAPP_URL` on the VPS set to the same public Pages URL if the Mini App is hosted there.

`AUTOVLESS_ORIGIN` must be the VPS origin, never the Pages URL, otherwise the proxy loops back into itself. The Pages Functions forward only `/sub/*` and `/dl/*`; all tunnel traffic still goes directly to each user's Cloudflare Worker.

## VPS commands

```bash
cd /opt/autovless
git pull origin main
# edit .env: PUBLIC_URL=https://pages-your-domain.example
# optional: WEBAPP_URL=https://pages-your-domain.example
docker compose up -d --build
docker compose logs --tail=100 autovless
```

## Smoke tests

```bash
curl -fsS https://pages-your-domain.example/api/health
curl -I https://pages-your-domain.example/sub/<token>
curl -I https://pages-your-domain.example/dl/<ticket>
```

The subscription response must be `200` or a deliberate auth response, not `503`. A `503` means the Pages variable is missing; a `502` or timeout means the VPS origin is not reachable over HTTPS.
