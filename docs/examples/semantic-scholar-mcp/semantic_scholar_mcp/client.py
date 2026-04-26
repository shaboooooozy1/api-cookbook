"""Async HTTP client for the Semantic Scholar API.

Centralises base URL selection, authentication header injection, timeout
handling, and 429/5xx retry-with-backoff so every tool can share the same
behaviour.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Literal

import httpx

from .constants import (
    API_KEY_ENV_VAR,
    DATASETS_API_BASE,
    DEFAULT_TIMEOUT_SECONDS,
    GRAPH_API_BASE,
    MAX_RETRIES,
    RECS_API_BASE,
    RETRY_BACKOFF_BASE_SECONDS,
)

ApiName = Literal["graph", "recs", "datasets"]

_BASE_URLS: dict[str, str] = {
    "graph": GRAPH_API_BASE,
    "recs": RECS_API_BASE,
    "datasets": DATASETS_API_BASE,
}


def get_api_key() -> str | None:
    """Return the configured API key, or ``None`` for anonymous access."""
    key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    return key or None


def _auth_headers() -> dict[str, str]:
    key = get_api_key()
    return {"x-api-key": key} if key else {}


async def request(
    method: str,
    path: str,
    *,
    api: ApiName = "graph",
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Make an authenticated request to a Semantic Scholar API.

    Retries on HTTP 429 and 5xx using exponential backoff, honouring any
    ``Retry-After`` header the server sends back.
    """
    base = _BASE_URLS[api]
    url = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    params = {k: v for k, v in (params or {}).items() if v is not None}

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, headers=_auth_headers()) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await client.request(method, url, params=params, json=json)
                if response.status_code in (429, 502, 503, 504) and attempt < MAX_RETRIES:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    await asyncio.sleep(
                        retry_after if retry_after is not None
                        else RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                    )
                    continue
                response.raise_for_status()
                if not response.content:
                    return {}
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise exc
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                if attempt >= MAX_RETRIES:
                    raise
                await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt))
    assert last_error is not None
    raise last_error


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def log_startup_mode() -> None:
    """Emit a one-line startup notice on stderr describing auth mode."""
    mode = "authenticated" if get_api_key() else "anonymous"
    print(
        f"[semantic_scholar_mcp] starting in {mode} mode "
        f"(set {API_KEY_ENV_VAR} for higher rate limits)",
        file=sys.stderr,
    )
