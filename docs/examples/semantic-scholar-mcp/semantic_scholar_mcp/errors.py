"""Shared error handling for the Semantic Scholar MCP server.

All tools funnel exceptions through :func:`handle_api_error` so responses are
consistent and actionable.
"""

from __future__ import annotations

import httpx


class SemanticScholarError(Exception):
    """Base error for Semantic Scholar operations."""


class MissingApiKeyError(SemanticScholarError):
    """Raised when an endpoint requires an API key that is not configured."""


def handle_api_error(exc: Exception) -> str:
    """Convert an exception into a user-facing error string.

    The message always starts with ``Error:`` so callers can distinguish
    failures from regular tool output when parsing markdown.
    """
    if isinstance(exc, MissingApiKeyError):
        return (
            "Error: This endpoint requires a Semantic Scholar API key. "
            "Set the SEMANTIC_SCHOLAR_API_KEY environment variable and "
            "restart the server. Request a key at "
            "https://www.semanticscholar.org/product/api#api-key"
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 400:
            return (
                "Error: Bad request (400). Check that all IDs, fields, and "
                "filter values are valid. Response: "
                f"{_truncate(exc.response.text)}"
            )
        if status == 401:
            return (
                "Error: Unauthorized (401). Your SEMANTIC_SCHOLAR_API_KEY "
                "appears invalid or revoked."
            )
        if status == 403:
            return (
                "Error: Forbidden (403). This resource is not accessible "
                "with the current credentials."
            )
        if status == 404:
            return (
                "Error: Resource not found (404). Double-check the paper "
                "or author ID. Supported paper ID formats: CorpusId, DOI, "
                "ARXIV:<id>, MAG:<id>, ACL:<id>, PMID:<id>, PMCID:<id>, "
                "URL:<url>."
            )
        if status == 429:
            return (
                "Error: Rate limit exceeded (429). Wait a few seconds and "
                "retry. Configure SEMANTIC_SCHOLAR_API_KEY for higher "
                "throughput."
            )
        if 500 <= status < 600:
            return (
                f"Error: Upstream Semantic Scholar server error ({status}). "
                "The API may be temporarily degraded; retry shortly."
            )
        return (
            f"Error: Semantic Scholar API returned HTTP {status}. "
            f"Response: {_truncate(exc.response.text)}"
        )
    if isinstance(exc, httpx.TimeoutException):
        return "Error: Request timed out. Retry or reduce the requested limit."
    if isinstance(exc, httpx.RequestError):
        return f"Error: Network error contacting Semantic Scholar: {exc!r}"
    if isinstance(exc, ValueError):
        return f"Error: {exc}"
    return f"Error: Unexpected {type(exc).__name__}: {exc}"


def _truncate(text: str, limit: int = 300) -> str:
    """Return *text* truncated to *limit* characters for compact error output."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
