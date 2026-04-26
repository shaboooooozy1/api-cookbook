"""Offline smoke tests.

These tests never touch the network. They verify that the server imports,
registers every tool with its expected name, and that Pydantic input schemas
behave correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from semantic_scholar_mcp.models import (
    BatchGetPapersInput,
    SearchPapersInput,
)
from semantic_scholar_mcp.server import mcp


EXPECTED_TOOLS = {
    "s2_search_papers",
    "s2_search_papers_bulk",
    "s2_match_paper_by_title",
    "s2_get_paper",
    "s2_get_paper_citations",
    "s2_get_paper_references",
    "s2_batch_get_papers",
    "s2_autocomplete_paper_title",
    "s2_search_authors",
    "s2_get_author",
    "s2_get_author_papers",
    "s2_batch_get_authors",
    "s2_recommend_from_paper",
    "s2_recommend_from_list",
    "s2_list_dataset_releases",
    "s2_get_release_datasets",
    "s2_get_dataset_download_links",
    "s2_resolve_identifier",
}


def _registered_tool_names() -> set[str]:
    for attr in ("tools", "_tools"):
        holder = getattr(mcp, attr, None)
        if isinstance(holder, dict) and holder:
            return set(holder.keys())
    manager = getattr(mcp, "_tool_manager", None)
    if manager is not None:
        inner = getattr(manager, "_tools", None)
        if isinstance(inner, dict):
            return set(inner.keys())
    raise AssertionError("Could not locate FastMCP tool registry")


def test_server_name() -> None:
    assert mcp.name == "semantic_scholar_mcp"


def test_all_tools_registered() -> None:
    names = _registered_tool_names()
    missing = EXPECTED_TOOLS - names
    assert not missing, f"Missing tools: {missing}"
    assert len(EXPECTED_TOOLS) == 18


def test_search_input_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchPapersInput(query="")


def test_search_input_clamps_limit() -> None:
    with pytest.raises(ValidationError):
        SearchPapersInput(query="x", limit=0)
    with pytest.raises(ValidationError):
        SearchPapersInput(query="x", limit=101)


def test_batch_get_papers_strips_empty_ids() -> None:
    model = BatchGetPapersInput(paper_ids=["abc", "  ", "def"])
    assert model.paper_ids == ["abc", "def"]


def test_batch_get_papers_rejects_all_empty() -> None:
    with pytest.raises(ValidationError):
        BatchGetPapersInput(paper_ids=["", "  "])
