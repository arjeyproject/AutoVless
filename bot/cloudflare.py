"""Thin async client for the Cloudflare API, scoped to what AutoVless needs."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import secrets
from typing import Any, Optional

import httpx

from .config import settings

log = logging.getLogger("autovless.cloudflare")

API = "https://api.cloudflare.com/client/v4"

REQUIRED_HINTS = (
    "Cloudflare Pages: Edit",
    "Workers Scripts: Edit",
    "Account Settings: Read",
    "Zone: Read",
    "Workers Routes: Edit",
)

# The Pages asset upload endpoints sit outside /accounts and authenticate with
# the short-lived upload token instead of the caller's API token.
PAGES_ASSET_UPLOAD = "/pages/assets/upload"
PAGES_ASSET_UPSERT = "/pages/assets/upsert-hashes"


class CloudflareError(Exception):
    """Raised when the Cloudflare API rejects a call."""

    def __init__(self, message: str, code: Optional[int] = None, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class RateLimitError(CloudflareError):
    """Raised when hitting Cloudflare rate limits."""

    def __init__(self, retry_after: Optional[float] = None) -> None:
        super().__init__("rate limit exceeded", status=429)
        self.retry_after = retry_after or 1.0


def _exponential_backoff(attempt: int, max_jitter: float = 0.1) -> float:
    """Exponential backoff with jitter: 2^attempt + random(0, max_jitter)."""
    base = min(2 ** attempt, 32)  # Cap at 32s
    jitter = random.uniform(0, max_jitter)
    return base + jitter


class CloudflareClient:
    def __init__(self, token: str, timeout: Optional[float] = None) -> None:
        self.token = token.strip()
        self._timeout = timeout or settings.request_timeout
        self._client: Optional[httpx.AsyncClient] = None
        # Circuit breaker: if too many failures in a row, fail fast
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5
        self._circuit_open_until = 0.0

    async def __aenter__(self) -> "CloudflareClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": f"{settings.brand}/1.0",
            },
        )
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make a Cloudflare API call with automatic backoff and rate limit handling."""
        if self._client is None:
            raise CloudflareError("client is not open")

        import time

        # Circuit breaker: if open, fail immediately
        now = time.time()
        if now < self._circuit_open_until:
            raise CloudflareError(
                f"circuit breaker open (will retry in {int(self._circuit_open_until - now)}s)"
            )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._client.request(method, f"{API}{path}", **kwargs)
            except httpx.TimeoutException as exc:
                raise CloudflareError("cloudflare timed out") from exc
            except httpx.HTTPError as exc:
                raise CloudflareError(f"network error: {exc}") from exc

            try:
                payload = response.json()
            except ValueError:
                raise CloudflareError(f"unexpected response ({response.status_code})", status=response.status_code)

            if isinstance(payload, dict) and payload.get("success"):
                self._consecutive_failures = 0
                return payload.get("result")

            # Handle rate limit (429) with backoff
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                if attempt < max_retries - 1:
                    wait = max(retry_after, _exponential_backoff(attempt))
                    await asyncio.sleep(wait)
                    continue
                # Final retry failed, raise rate limit error
                raise RateLimitError(retry_after)

            # Handle 5xx errors with backoff
            if 500 <= response.status_code < 600:
                if attempt < max_retries - 1:
                    wait = _exponential_backoff(attempt)
                    await asyncio.sleep(wait)
                    continue

            # Non-retryable error or final attempt
            errors = payload.get("errors") or [] if isinstance(payload, dict) else []
            first = errors[0] if errors else {}
            message = first.get("message") or f"cloudflare returned {response.status_code}"
            self._consecutive_failures += 1

            # Open circuit if too many consecutive failures
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._circuit_open_until = time.time() + 60  # Open for 60s
                raise CloudflareError(f"circuit breaker activated: {message}")

            raise CloudflareError(message, code=first.get("code"), status=response.status_code)

        raise CloudflareError("max retries exceeded")

    # ------------------------------------------------------------------ #
    # identity
    # ------------------------------------------------------------------ #

    async def verify_token(self) -> dict:
        result = await self._call("GET", "/user/tokens/verify")
        if isinstance(result, dict) and result.get("status") not in (None, "active"):
            raise CloudflareError(f"token status is '{result.get('status')}'")
        return result or {}

    async def first_account(self) -> dict:
        accounts = await self._call("GET", "/accounts", params={"per_page": 50})
        if not accounts:
            raise CloudflareError("no account is reachable with this token")
        return accounts[0]

    # ------------------------------------------------------------------ #
    # workers.dev subdomain
    # ------------------------------------------------------------------ #

    async def get_subdomain(self, account_id: str) -> str:
        try:
            result = await self._call("GET", f"/accounts/{account_id}/workers/subdomain")
        except CloudflareError as exc:
            if exc.status in (403, 404) or exc.code in (10007, 10021):
                return ""
            raise
        return (result or {}).get("subdomain") or ""

    async def claim_subdomain(self, account_id: str) -> str:
        for _ in range(6):
            candidate = f"avl-{secrets.token_hex(3)}"
            try:
                result = await self._call(
                    "PUT",
                    f"/accounts/{account_id}/workers/subdomain",
                    json={"subdomain": candidate},
                )
            except CloudflareError as exc:
                if exc.code in (10034, 10035) or "taken" in exc.message.lower():
                    continue
                raise
            return (result or {}).get("subdomain") or candidate
        raise CloudflareError("could not reserve a workers.dev subdomain")

    async def ensure_subdomain(self, account_id: str) -> str:
        subdomain = await self.get_subdomain(account_id)
        if subdomain:
            return subdomain
        return await self.claim_subdomain(account_id)

    # ------------------------------------------------------------------ #
    # zones and custom domains
    # ------------------------------------------------------------------ #

    async def list_zones(self, account_id: str) -> list[dict]:
        """Zones this token can see on the account. Empty on a missing permission."""
        try:
            result = await self._call(
                "GET",
                "/zones",
                params={"account.id": account_id, "per_page": 50},
            )
        except CloudflareError as exc:
            if exc.status in (401, 403, 404):
                return []
            raise
        return [zone for zone in (result or []) if isinstance(zone, dict)]

    async def attach_domain(
        self,
        account_id: str,
        zone_id: str,
        zone_name: str,
        hostname: str,
        script_name: str,
    ) -> dict:
        """Workers Custom Domain: Cloudflare creates the DNS record and the cert."""
        result = await self._call(
            "PUT",
            f"/accounts/{account_id}/workers/domains",
            json={
                "environment": "production",
                "hostname": hostname,
                "service": script_name,
                "zone_id": zone_id,
                "zone_name": zone_name,
            },
        )
        return result or {}

    async def list_worker_domains(self, account_id: str) -> list[dict]:
        """Every Workers custom-domain binding on the account."""
        result = await self._call("GET", f"/accounts/{account_id}/workers/domains")
        return result or []

    async def detach_worker_domain(self, account_id: str, domain_id: str) -> None:
        """Remove one Workers custom-domain binding.

        Deleting the script alone leaves the binding behind: the hostname keeps
        pointing at a service that no longer exists and Cloudflare answers 522
        to everything, which reads to the user as "the bot died" long after the
        panel was removed. Detaching is the other half of every delete.
        """
        try:
            await self._call(
                "DELETE", f"/accounts/{account_id}/workers/domains/{domain_id}"
            )
        except CloudflareError as exc:
            if exc.status != 404:
                raise

    # ------------------------------------------------------------------ #
    # worker scripts
    # ------------------------------------------------------------------ #

    async def list_scripts(self, account_id: str) -> list[dict]:
        result = await self._call("GET", f"/accounts/{account_id}/workers/scripts")
        return result or []

    async def upload_script(
        self,
        account_id: str,
        script_name: str,
        code: str,
        variables: dict[str, str],
    ) -> dict:
        metadata = {
            "main_module": "worker.js",
            "compatibility_date": settings.compatibility_date,
            "bindings": [
                {"type": "plain_text", "name": name, "text": str(value)}
                for name, value in variables.items()
            ],
        }
        files = {
            "metadata": (None, json.dumps(metadata), "application/json"),
            "worker.js": ("worker.js", code.encode("utf-8"), "application/javascript+module"),
        }
        result = await self._call(
            "PUT",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
            files=files,
        )
        return result or {}

    async def enable_workers_dev(self, account_id: str, script_name: str) -> None:
        await self._call(
            "POST",
            f"/accounts/{account_id}/workers/scripts/{script_name}/subdomain",
            json={"enabled": True, "previews_enabled": False},
        )

    async def delete_script(self, account_id: str, script_name: str) -> None:
        try:
            await self._call(
                "DELETE",
                f"/accounts/{account_id}/workers/scripts/{script_name}",
                params={"force": "true"},
            )
        except CloudflareError as exc:
            if exc.status == 404:
                return
            raise

    # ------------------------------------------------------------------ #
    # pages projects
    # ------------------------------------------------------------------ #

    async def get_pages_project(self, account_id: str, project: str) -> Optional[dict]:
        try:
            result = await self._call(
                "GET", f"/accounts/{account_id}/pages/projects/{project}"
            )
        except CloudflareError as exc:
            if exc.status == 404:
                return None
            raise
        return result or {}

    async def create_pages_project(self, account_id: str, project: str) -> dict:
        result = await self._call(
            "POST",
            f"/accounts/{account_id}/pages/projects",
            json={"name": project, "production_branch": "main"},
        )
        return result or {}

    async def update_pages_env(
        self, account_id: str, project: str, variables: dict[str, str]
    ) -> None:
        """Project-level production env vars. Deployments inherit them at build time."""
        await self._call(
            "PATCH",
            f"/accounts/{account_id}/pages/projects/{project}",
            json={
                "deployment_configs": {
                    "production": {
                        "env_vars": {
                            name: {"type": "plain_text", "value": str(value)}
                            for name, value in variables.items()
                        }
                    }
                }
            },
        )

    async def upload_pages_assets(
        self, account_id: str, project: str, files: list[dict]
    ) -> None:
        """Direct upload: token, payload buckets, hash upsert.

        ``files`` is a list of {"path", "contents" (bytes), "contentType"}.
        The JWT from the upload-token endpoint authenticates the two asset
        calls; upsert-hashes is what flips them to reusable.
        """
        token_result = await self._call(
            "GET", f"/accounts/{account_id}/pages/projects/{project}/upload-token"
        )
        jwt = str((token_result or {}).get("jwt") or "")

        payloads = [
            {
                "key": item["hash"],
                "value": base64.b64encode(item["contents"]).decode("ascii"),
                "metadata": {"contentType": item["contentType"]},
                "base64": True,
            }
            for item in files
        ]
        if payloads:
            await self._call(
                "POST",
                PAGES_ASSET_UPLOAD,
                json=payloads,
                headers={"Authorization": f"Bearer {jwt}"},
            )
        await self._call(
            "POST",
            PAGES_ASSET_UPSERT,
            json={"hashes": [item["hash"] for item in files]},
            headers={"Authorization": f"Bearer {jwt}"},
        )

    @staticmethod
    def _undici_multipart(parts: list[tuple[str, Optional[str], Optional[bytes], Optional[str]]], boundary: str) -> bytes:
        """Serialise parts exactly the way undici's FormData does.

        ``parts`` entries are ``(name, filename, content, content_type)``; a
        ``None`` filename makes a plain form field and a ``None`` content type
        leaves the header off entirely - both material details, because the
        Pages parser is exact about which parts carry headers.
        """
        out = []
        for name, filename, content, ctype in parts:
            head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            if filename:
                head += f'; filename="{filename}"'
            head += "\r\n"
            if ctype:
                head += f"Content-Type: {ctype}\r\n"
            head += "\r\n"
            out.append(head.encode("utf-8") + (content or b"") + b"\r\n")
        out.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(out)

    async def create_pages_deployment(
        self,
        account_id: str,
        project: str,
        code: bytes,
    ) -> dict:
        """One deployment of an advanced-mode (``_worker.js``) Pages project.

        The upload is a NESTED multipart, and the nesting is the part every
        previous attempt got wrong (2026-11-07). wrangler does not send the
        worker source as the ``_worker.bundle`` field - it serialises the
        classic Workers script upload form (``createWorkerUploadForm``:
        a ``metadata`` field plus one part per module) into a blob with
        ``await new Response(formData).blob()`` and appends THAT as
        ``_worker.bundle``. The platform then unwraps the outer multipart,
        reads the bundle, and parses ITS ``metadata`` JSON - which is exactly
        why a flat body with plain JS inside was always answered with
        "Request body is incorrect. The request body may have an invalid JSON
        type or missing required keys": the inner ``metadata`` never parsed.

        Outer form, field order per wrangler ``api/pages/deploy.ts``:
          - ``manifest``  plain field, ``{}`` (no static assets)
          - ``branch``    plain field, ``main``
          - ``_worker.bundle`` file part, filename ``_worker.bundle``, NO
            Content-Type header (``new File(..., "_worker.bundle")`` has an
            empty type and undici omits the header when the type is empty)

        Inner form (the bundle), per ``deploy-helpers/create-worker-upload-form.ts``:
          - ``metadata``  plain field: ``{"main_module": "worker.js"}`` - no
            bindings key at all (env vars ride on the project's
            ``deployment_configs``, exactly like a Pages deploy without a
            wrangler config)
          - ``worker.js`` file part, filename ``worker.js``,
            Content-Type ``application/javascript+module``

        A ``_worker.js`` entry in the asset manifest would be SERVED
        STATICALLY instead of run, which is what the "deployed but never
        answers" builds were doing; the bundle field is the only shape the
        platform executes.
        """
        inner_boundary = f"----formdata-undici-{secrets.token_hex(12)}"
        inner = self._undici_multipart(
            [
                ("metadata", None, json.dumps({"main_module": "worker.js"}).encode(), None),
                ("worker.js", "worker.js", code, "application/javascript+module"),
            ],
            inner_boundary,
        )
        outer_boundary = f"----formdata-undici-{secrets.token_hex(12)}"
        body = self._undici_multipart(
            [
                ("manifest", None, b"{}", None),
                ("branch", None, b"main", None),
                ("_worker.bundle", "_worker.bundle", inner, None),
            ],
            outer_boundary,
        )
        result = await self._call(
            "POST",
            f"/accounts/{account_id}/pages/projects/{project}/deployments",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={outer_boundary}"},
        )
        return result or {}

    async def attach_pages_domain(self, account_id: str, project: str, hostname: str) -> dict:
        result = await self._call(
            "POST",
            f"/accounts/{account_id}/pages/projects/{project}/domains",
            json={"name": hostname},
        )
        return result or {}

    async def detach_pages_domain(self, account_id: str, project: str, hostname: str) -> None:
        """Remove one custom domain from a Pages project."""
        try:
            await self._call(
                "DELETE",
                f"/accounts/{account_id}/pages/projects/{project}/domains/{hostname}",
            )
        except CloudflareError as exc:
            if exc.status != 404:
                raise

    async def list_pages_domains(self, account_id: str, project: str) -> list[str]:
        """The hostnames attached to a Pages project."""
        try:
            result = await self._call(
                "GET", f"/accounts/{account_id}/pages/projects/{project}/domains"
            )
        except CloudflareError as exc:
            if exc.status == 404:
                return []
            raise
        return [
            str(row.get("name"))
            for row in (result or [])
            if isinstance(row, dict) and row.get("name")
        ]

    async def list_pages_deployments(
        self,
        account_id: str,
        project: str,
        limit: int = 5,
    ) -> list[dict]:
        """Newest first. Used to watch a deployment until it actually goes live."""
        result = await self._call(
            "GET",
            f"/accounts/{account_id}/pages/projects/{project}/deployments",
            params={"page": 1, "per_page": max(1, min(25, limit))},
        )
        return result or []

    async def upsert_zone_cname(
        self,
        zone_id: str,
        hostname: str,
        target: str,
        proxied: bool = True,
    ) -> dict:
        """Create the CNAME a Pages custom domain waits for, or update it.

        Pages domains created through the API on a zone inside the same account
        do not get a DNS record for free - the project domain sits "pending"
        until one exists. Idempotent: an existing record of the same type and
        name is updated, not duplicated.
        """
        existing: list[dict] = []
        try:
            listing = await self._call(
                "GET",
                f"/zones/{zone_id}/dns_records",
                params={"type": "CNAME", "name": hostname, "per_page": 50},
            )
            existing = listing or []
        except CloudflareError as error:
            log.info("dns listing failed for %s: %s", hostname, error.message)

        payload = {
            "type": "CNAME",
            "name": hostname,
            "content": target,
            "ttl": 1,  # 1 = auto, required when proxied
            "proxied": proxied,
        }
        if existing:
            record_id = str(existing[0]["id"])
            result = await self._call(
                "PUT", f"/zones/{zone_id}/dns_records/{record_id}", json=payload
            )
            log.info("updated dns cname %s -> %s", hostname, target)
            return result or {}
        result = await self._call(
            "POST", f"/zones/{zone_id}/dns_records", json=payload
        )
        log.info("created dns cname %s -> %s", hostname, target)
        return result or {}

    async def delete_pages_project(self, account_id: str, project: str) -> None:
        try:
            await self._call(
                "DELETE", f"/accounts/{account_id}/pages/projects/{project}"
            )
        except CloudflareError as exc:
            if exc.status == 404:
                return
            raise


def token_looks_valid(raw: str) -> bool:
    """Cheap client-side sanity check before burning an API round trip."""
    token = raw.strip()
    if len(token) < 32 or len(token) > 120:
        return False
    if " " in token or "\n" in token:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    return set(token) <= allowed


def script_name() -> str:
    return f"auto-{secrets.randbelow(900000) + 100000}"
