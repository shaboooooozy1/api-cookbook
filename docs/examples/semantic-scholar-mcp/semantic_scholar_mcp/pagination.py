"""Pagination helpers shared across tools."""

from __future__ import annotations

from typing import Any


def build_offset_page(
    *,
    items: list[dict[str, Any]],
    offset: int,
    limit: int,
    total: int | None,
) -> dict[str, Any]:
    """Return an offset-based pagination envelope."""
    next_offset: int | None = None
    has_more = False
    if total is not None:
        has_more = offset + len(items) < total
        next_offset = offset + len(items) if has_more else None
    else:
        has_more = len(items) == limit
        next_offset = offset + len(items) if has_more else None
    return {
        "total": total,
        "count": len(items),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_offset": next_offset,
        "items": items,
    }


def build_token_page(
    *,
    items: list[dict[str, Any]],
    token: str | None,
    next_token: str | None,
    total: int | None,
) -> dict[str, Any]:
    """Return a token-based pagination envelope (for /paper/search/bulk)."""
    return {
        "total": total,
        "count": len(items),
        "token": token,
        "next_token": next_token,
        "has_more": next_token is not None,
        "items": items,
    }
