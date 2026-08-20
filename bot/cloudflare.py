"""Thin async client for the Cloudflare API, scoped to what AutoVless needs."""

from __future__ import annotations

import json
import secrets
from typing import Any, Optional

import httpx

from .config import settings

API = "https://api.cloudflare.com/client/v4"

REQUIRED_HINTS = (
    "Workers Scripts: Edit",
    "Account Settings: Read",
)


class CloudflareError(Exception):
    """Raised when the Cloudflare API rejects a call."""

    def __init__(self, message: str, code: Optional[int] = None, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class CloudflareClient:
    def __init__(self, token: str, timeout: Optional[float] = None) -> None:
        self.token = token.strip()
        self._timeout = timeout or settings.request_timeout
        self._client: Optional[httpx.AsyncClient] = None

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
        if self._client is None:
            raise CloudflareError("client is not open")
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
            return payload.get("result")

        errors = payload.get("errors") or [] if isinstance(payload, dict) else []
        first = errors[0] if errors else {}
        message = first.get("message") or f"cloudflare returned {response.status_code}"
        raise CloudflareError(message, code=first.get("code"), status=response.status_code)

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
