"""Deploy a panel as a Cloudflare Pages project instead of a Worker.

Why Pages
---------
The panel's code is unchanged: a Pages project in advanced mode runs the same
``_worker.js`` module on the same V8 runtime, with the same ``env`` bindings.
What changes is the platform around it:

  * the project lives on the user's own Cloudflare Pages, so the free request
    allowance and the abuse surface sit with their account, exactly like a
    Worker did;
  * the built-in front door is ``<project>.pages.dev`` instead of
    ``<script>.<subdomain>.workers.dev``;
  * a custom domain attaches through the Pages domains API and Cloudflare
    creates the DNS record and the certificate itself;
  * bindings ride on the project's production ``deployment_configs``, so a
    refresh updates the vars first and then pushes one new deployment;
  * Pages free plan allows a bounded number of deployments per month, so the
    autopilot refreshes Pages panels on a slower cadence than Workers panels.
    The worker's own live subscription blending keeps the configs fresh in
    between.

The upload protocol is the same one wrangler performs: an upload token, the
asset payloads keyed by their ``blake3(base64 + extension)`` hash, an upsert
of those hashes, then a deployment whose manifest maps bundle paths to hashes.
"""

from __future__ import annotations

import logging

from . import blake3pure, vless
from .cloudflare import CloudflareClient, CloudflareError

log = logging.getLogger("autovless.pages")

PAGES_SUFFIX = ".pages.dev"
WORKER_BUNDLE = "_worker.js"

# Pages env vars are plain text; the deployment snapshots whatever the project
# holds when it is created, so every re-deploy updates the vars first.
WORKER_CONTENT_TYPE = "text/javascript"


class PagesError(Exception):
    """Raised when a Pages deployment cannot be completed."""


def is_pages_host(host: object) -> bool:
    return str(host or "").strip().lower().endswith(PAGES_SUFFIX)


def project_name(seed: str) -> str:
    """A Pages-safe project name derived from the panel's script name.

    Pages names are lowercase letters, digits and dashes. The panel's
    ``auto-XXXXXX`` script name already fits, and reusing it keeps the project
    and any Worker fallback distinguishable while staying stable across
    rebuilds.
    """
    cleaned = "".join(ch for ch in str(seed).lower() if ch.isalnum() or ch == "-")
    return cleaned or "autovless"


def host_for(project: str) -> str:
    return f"{project}{PAGES_SUFFIX}"


async def _ensure_project(cf: CloudflareClient, account_id: str, project: str) -> None:
    existing = await cf.get_pages_project(account_id, project)
    if existing:
        return
    await cf.create_pages_project(account_id, project)


async def _bundle(code: str) -> bytes:
    """The Pages deployment carries exactly one file: the worker module."""
    return code.encode("utf-8")


async def push(
    token: str,
    account_id: str,
    project: str,
    code: str,
    variables: dict[str, str],
) -> str:
    """Update bindings, then create one production deployment. Returns the host."""
    try:
        async with CloudflareClient(token) as cf:
            await _ensure_project(cf, account_id, project)
            await cf.update_pages_env(account_id, project, variables)

            contents = await _bundle(code)
            digest = blake3pure.file_hash(WORKER_BUNDLE, contents)
            await cf.upload_pages_assets(
                account_id,
                project,
                [
                    {
                        "path": WORKER_BUNDLE,
                        "contents": contents,
                        "hash": digest,
                        "contentType": WORKER_CONTENT_TYPE,
                    }
                ],
            )
            await cf.create_pages_deployment(
                account_id, project, {f"/{WORKER_BUNDLE}": digest}
            )
    except CloudflareError as error:
        raise PagesError(error.message) from error
    return host_for(project)


async def attach_domain(cf: CloudflareClient, account_id: str, project: str) -> str:
    """Attach ``<label>.<zone>`` to the Pages project. ``""`` when impossible."""
    from . import edge

    if not edge.enabled():
        return ""
    try:
        zone = await edge.pick_zone(cf, account_id)
    except CloudflareError as error:
        log.info("zone lookup failed for %s: %s", account_id, error.message)
        return ""
    if not zone:
        log.info("account %s has no active zone; panel stays on pages.dev", account_id)
        return ""

    hostname = f"{edge.label_for(project)}.{str(zone['name']).lower()}"
    try:
        await cf.attach_pages_domain(account_id, project, hostname)
    except CloudflareError as error:
        log.warning("could not attach %s to project %s: %s", hostname, project, error.message)
        return ""
    log.info("attached pages domain %s -> %s", hostname, project)
    return hostname


async def destroy(token: str, account_id: str, project: str) -> None:
    try:
        async with CloudflareClient(token) as cf:
            await cf.delete_pages_project(account_id, project)
    except CloudflareError as error:
        raise PagesError(error.message) from error


def bindings(
    uuid: str,
    host: str,
    endpoints: list[dict],
    relays: list[str],
    ai_relays: list[str],
    chain_relays: list[str] | None = None,
) -> dict[str, str]:
    """The env vars a Pages panel carries. Built once, shared with deploy."""
    from .deploy import _bindings  # the single source of the worker's var list

    return _bindings(uuid, host, endpoints, relays, ai_relays, chain_relays)


def panel_vars(panel: dict, endpoints: list[dict], relays: list[str]) -> dict[str, str]:
    """Rebuild the env vars for a stored panel row at refresh time."""
    return bindings(
        str(panel["uuid"]),
        str(panel["host"]),
        endpoints,
        relays,
        [str(panel.get("ai_relay") or "")] if panel.get("ai_relay") else [],
        [str(panel.get("chain_relay") or "")] if panel.get("chain_relay") else [],
    )


def link_overview(uuid: str, host: str) -> dict[str, str]:
    """The subscription URLs a Pages panel serves, named for the UI."""
    return {
        "vless": vless.sub_url(uuid, host),
        "httpupgrade": vless.sub_url(uuid, host, "httpup"),
        "xhttp": vless.sub_url(uuid, host, "xhttp"),
        "trojan": vless.sub_url(uuid, host, "trojan"),
        "ss": vless.sub_url(uuid, host, "ss"),
        "mix": vless.sub_url(uuid, host, "mix"),
        "clash": vless.sub_url(uuid, host, "clash"),
        "singbox": vless.sub_url(uuid, host, "singbox"),
    }


__all__ = [
    "PagesError",
    "PAGES_SUFFIX",
    "WORKER_BUNDLE",
    "attach_domain",
    "bindings",
    "destroy",
    "host_for",
    "is_pages_host",
    "link_overview",
    "panel_vars",
    "project_name",
    "push",
]
