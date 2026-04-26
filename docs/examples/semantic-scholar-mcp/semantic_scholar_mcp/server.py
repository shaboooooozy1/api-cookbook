"""FastMCP server exposing comprehensive Semantic Scholar tools and resources."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import client
from .constants import (
    DEFAULT_AUTHOR_FIELDS, DEFAULT_AUTHOR_PAPERS_FIELDS,
    DEFAULT_PAPER_FIELDS, DEFAULT_PAPER_LIST_FIELDS,
)
from .errors import MissingApiKeyError, handle_api_error
from .formatting import (
    ResponseFormat, as_json, extract_citation_papers,
    extract_reference_papers, format_author, format_author_list,
    format_paper, format_paper_list,
)
from .models import (
    AutocompletePaperTitleInput, BatchGetAuthorsInput, BatchGetPapersInput,
    GetAuthorInput, GetAuthorPapersInput, GetDatasetDownloadLinksInput,
    GetPaperInput, GetReleaseDatasetsInput, ListDatasetReleasesInput,
    MatchPaperByTitleInput, PaperPaginatedInput, RecommendFromListInput,
    RecommendFromPaperInput, ResolveIdentifierInput, SearchAuthorsInput,
    SearchPapersBulkInput, SearchPapersInput,
)
from .pagination import build_offset_page, build_token_page

mcp = FastMCP("semantic_scholar_mcp")

READ_ONLY_ANNOTATIONS: dict[str, bool | str] = {
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": True,
}


@mcp.tool(name="s2_search_papers", annotations={"title": "Search Semantic Scholar papers", **READ_ONLY_ANNOTATIONS})
async def s2_search_papers(params: SearchPapersInput) -> str:
    """Relevance-ranked paper search over the Semantic Scholar corpus."""
    try:
        data = await client.request("GET", "/paper/search", params={
            "query": params.query, "limit": params.limit, "offset": params.offset,
            "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS, "year": params.year,
            "venue": params.venue, "fieldsOfStudy": params.fields_of_study,
            "openAccessPdf": "true" if params.open_access_pdf else None,
        })
        papers = data.get("data", []) or []
        envelope = build_offset_page(items=papers, offset=params.offset, limit=params.limit, total=data.get("total"))
        return format_paper_list(papers, fmt=params.response_format, title=f"Search results: {params.query!r}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_search_papers_bulk", annotations={"title": "Bulk search Semantic Scholar papers", **READ_ONLY_ANNOTATIONS})
async def s2_search_papers_bulk(params: SearchPapersBulkInput) -> str:
    """Token-paginated bulk search, up to 1000 papers per page."""
    try:
        data = await client.request("GET", "/paper/search/bulk", params={
            "query": params.query, "token": params.token, "limit": params.limit,
            "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS, "year": params.year,
            "venue": params.venue, "fieldsOfStudy": params.fields_of_study, "sort": params.sort,
        })
        papers = data.get("data", []) or []
        envelope = build_token_page(items=papers, token=params.token, next_token=data.get("token"), total=data.get("total"))
        return format_paper_list(papers, fmt=params.response_format, title=f"Bulk search: {params.query!r}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_match_paper_by_title", annotations={"title": "Match paper by exact title", **READ_ONLY_ANNOTATIONS})
async def s2_match_paper_by_title(params: MatchPaperByTitleInput) -> str:
    """Return the best single-paper match for an exact-title lookup."""
    try:
        data = await client.request("GET", "/paper/search/match", params={"query": params.title, "fields": params.fields or DEFAULT_PAPER_FIELDS})
        match = (data.get("data") or [None])[0]
        if not match:
            return f"Error: No confident title match for {params.title!r}."
        return format_paper(match, params.response_format)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_paper", annotations={"title": "Get Semantic Scholar paper by ID", **READ_ONLY_ANNOTATIONS})
async def s2_get_paper(params: GetPaperInput) -> str:
    """Fetch full details for a paper by any accepted identifier."""
    try:
        data = await client.request("GET", f"/paper/{params.paper_id}", params={"fields": params.fields or DEFAULT_PAPER_FIELDS})
        return format_paper(data, params.response_format)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_paper_citations", annotations={"title": "List papers citing a paper", **READ_ONLY_ANNOTATIONS})
async def s2_get_paper_citations(params: PaperPaginatedInput) -> str:
    """Return papers that cite the given paper (offset-paginated)."""
    try:
        data = await client.request("GET", f"/paper/{params.paper_id}/citations", params={"limit": params.limit, "offset": params.offset, "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS})
        raw = data.get("data", []) or []
        papers = extract_citation_papers(raw)
        envelope = build_offset_page(items=papers, offset=data.get("offset", params.offset), limit=params.limit, total=data.get("total"))
        return format_paper_list(papers, fmt=params.response_format, title=f"Citations of {params.paper_id}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_paper_references", annotations={"title": "List references of a paper", **READ_ONLY_ANNOTATIONS})
async def s2_get_paper_references(params: PaperPaginatedInput) -> str:
    """Return papers referenced by the given paper (offset-paginated)."""
    try:
        data = await client.request("GET", f"/paper/{params.paper_id}/references", params={"limit": params.limit, "offset": params.offset, "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS})
        raw = data.get("data", []) or []
        papers = extract_reference_papers(raw)
        envelope = build_offset_page(items=papers, offset=data.get("offset", params.offset), limit=params.limit, total=data.get("total"))
        return format_paper_list(papers, fmt=params.response_format, title=f"References of {params.paper_id}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_batch_get_papers", annotations={"title": "Batch fetch papers", **READ_ONLY_ANNOTATIONS})
async def s2_batch_get_papers(params: BatchGetPapersInput) -> str:
    """Fetch up to 500 papers in a single call."""
    try:
        data = await client.request("POST", "/paper/batch", params={"fields": params.fields or DEFAULT_PAPER_FIELDS}, json={"ids": params.paper_ids})
        papers = data if isinstance(data, list) else []
        if params.response_format is ResponseFormat.JSON:
            return as_json({"count": len(papers), "items": papers})
        resolved = [p for p in papers if p]
        missing = len(papers) - len(resolved)
        envelope = {"total": len(papers), "count": len(resolved), "offset": 0, "has_more": False}
        title = f"Batch paper lookup ({len(resolved)}/{len(papers)} resolved"
        if missing:
            title += f", {missing} missing"
        title += ")"
        return format_paper_list(resolved, fmt=params.response_format, title=title, envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_autocomplete_paper_title", annotations={"title": "Autocomplete paper titles", **READ_ONLY_ANNOTATIONS})
async def s2_autocomplete_paper_title(params: AutocompletePaperTitleInput) -> str:
    """Return title-autocomplete suggestions."""
    try:
        data = await client.request("GET", "/paper/autocomplete", params={"query": params.query})
        matches = data.get("matches") if isinstance(data, dict) else data
        matches = matches or []
        if params.response_format is ResponseFormat.JSON:
            return as_json({"count": len(matches), "items": matches})
        if not matches:
            return f"# Autocomplete: {params.query!r}\n\n_No suggestions._"
        lines = [f"# Autocomplete: {params.query!r}", ""]
        for i, m in enumerate(matches, 1):
            pid = m.get("id") or m.get("paperId")
            title = m.get("title") or "(untitled)"
            year = m.get("year")
            suffix = f" -- {year}" if year else ""
            lines.append(f"{i}. **{title}**{suffix} (id: {pid})")
        return "\n".join(lines) + "\n"
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_search_authors", annotations={"title": "Search authors", **READ_ONLY_ANNOTATIONS})
async def s2_search_authors(params: SearchAuthorsInput) -> str:
    """Search for authors by name or name fragment."""
    try:
        data = await client.request("GET", "/author/search", params={"query": params.query, "limit": params.limit, "offset": params.offset, "fields": params.fields or DEFAULT_AUTHOR_FIELDS})
        authors = data.get("data", []) or []
        envelope = build_offset_page(items=authors, offset=params.offset, limit=params.limit, total=data.get("total"))
        return format_author_list(authors, fmt=params.response_format, title=f"Author search: {params.query!r}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_author", annotations={"title": "Get author profile", **READ_ONLY_ANNOTATIONS})
async def s2_get_author(params: GetAuthorInput) -> str:
    """Return full author profile."""
    try:
        data = await client.request("GET", f"/author/{params.author_id}", params={"fields": params.fields or DEFAULT_AUTHOR_FIELDS})
        return format_author(data, params.response_format)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_author_papers", annotations={"title": "List papers by author", **READ_ONLY_ANNOTATIONS})
async def s2_get_author_papers(params: GetAuthorPapersInput) -> str:
    """Return papers authored by a given Semantic Scholar author ID."""
    try:
        data = await client.request("GET", f"/author/{params.author_id}/papers", params={"limit": params.limit, "offset": params.offset, "fields": params.fields or DEFAULT_AUTHOR_PAPERS_FIELDS})
        papers = data.get("data", []) or []
        envelope = build_offset_page(items=papers, offset=data.get("offset", params.offset), limit=params.limit, total=data.get("total"))
        return format_paper_list(papers, fmt=params.response_format, title=f"Papers by author {params.author_id}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_batch_get_authors", annotations={"title": "Batch fetch authors", **READ_ONLY_ANNOTATIONS})
async def s2_batch_get_authors(params: BatchGetAuthorsInput) -> str:
    """Fetch up to 500 author profiles in a single call."""
    try:
        data = await client.request("POST", "/author/batch", params={"fields": params.fields or DEFAULT_AUTHOR_FIELDS}, json={"ids": params.author_ids})
        authors = data if isinstance(data, list) else []
        if params.response_format is ResponseFormat.JSON:
            return as_json({"count": len(authors), "items": authors})
        resolved = [a for a in authors if a]
        missing = len(authors) - len(resolved)
        envelope = {"total": len(authors), "count": len(resolved), "offset": 0, "has_more": False}
        title = f"Batch author lookup ({len(resolved)}/{len(authors)} resolved"
        if missing:
            title += f", {missing} missing"
        title += ")"
        return format_author_list(resolved, fmt=params.response_format, title=title, envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_recommend_from_paper", annotations={"title": "Recommend papers like one paper", **READ_ONLY_ANNOTATIONS})
async def s2_recommend_from_paper(params: RecommendFromPaperInput) -> str:
    """Return papers similar to a seed paper."""
    try:
        data = await client.request("GET", f"/papers/forpaper/{params.paper_id}", api="recs", params={"limit": params.limit, "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS, "from": "recent" if params.recent_only else "all-cs"})
        papers = data.get("recommendedPapers", []) or []
        envelope = {"total": len(papers), "count": len(papers), "offset": 0, "limit": params.limit, "has_more": False, "next_offset": None}
        return format_paper_list(papers, fmt=params.response_format, title=f"Papers recommended from {params.paper_id}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_recommend_from_list", annotations={"title": "Recommend papers from positive/negative lists", **READ_ONLY_ANNOTATIONS})
async def s2_recommend_from_list(params: RecommendFromListInput) -> str:
    """Return papers similar to a positive list and dissimilar to a negative list."""
    try:
        body = {"positivePaperIds": params.positive_paper_ids, "negativePaperIds": params.negative_paper_ids or []}
        data = await client.request("POST", "/papers", api="recs", params={"limit": params.limit, "fields": params.fields or DEFAULT_PAPER_LIST_FIELDS}, json=body)
        papers = data.get("recommendedPapers", []) or []
        envelope = {"total": len(papers), "count": len(papers), "offset": 0, "limit": params.limit, "has_more": False, "next_offset": None}
        return format_paper_list(papers, fmt=params.response_format, title="Recommended papers from positive/negative lists", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_list_dataset_releases", annotations={"title": "List dataset releases", **READ_ONLY_ANNOTATIONS})
async def s2_list_dataset_releases(params: ListDatasetReleasesInput) -> str:
    """List all available Semantic Scholar dataset releases."""
    try:
        data = await client.request("GET", "/release/", api="datasets")
        releases = data if isinstance(data, list) else []
        if params.response_format is ResponseFormat.JSON:
            return as_json({"count": len(releases), "items": releases})
        if not releases:
            return "# Dataset releases\n\n_No releases available._"
        lines = [f"# Dataset releases ({len(releases)} total)", ""]
        for r in releases[-20:]:
            lines.append(f"- `{r}`")
        if len(releases) > 20:
            lines.append(f"\n_...showing most recent 20 of {len(releases)}._")
        return "\n".join(lines) + "\n"
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_release_datasets", annotations={"title": "List datasets in a release", **READ_ONLY_ANNOTATIONS})
async def s2_get_release_datasets(params: GetReleaseDatasetsInput) -> str:
    """List datasets available in a specific release."""
    try:
        data = await client.request("GET", f"/release/{params.release_id}", api="datasets")
        if params.response_format is ResponseFormat.JSON:
            return as_json(data)
        datasets = data.get("datasets") or []
        lines = [f"# Release {data.get('release_id', params.release_id)}", ""]
        if data.get("README"):
            lines.append(data["README"].strip())
            lines.append("")
        lines.append(f"**Datasets ({len(datasets)}):**")
        for d in datasets:
            name = d.get("name", "(unknown)")
            desc = d.get("description", "").strip()
            lines.append(f"- **{name}** -- {desc}" if desc else f"- **{name}**")
        return "\n".join(lines).rstrip() + "\n"
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_get_dataset_download_links", annotations={"title": "Get dataset download links", **READ_ONLY_ANNOTATIONS})
async def s2_get_dataset_download_links(params: GetDatasetDownloadLinksInput) -> str:
    """Return temporary S3 download URLs for a dataset. Requires API key."""
    try:
        if not client.get_api_key():
            raise MissingApiKeyError("dataset download links require an API key")
        data = await client.request("GET", f"/release/{params.release_id}/dataset/{params.dataset_name}", api="datasets")
        if params.response_format is ResponseFormat.JSON:
            return as_json(data)
        files = data.get("files") or []
        lines = [f"# Download links: {params.release_id}/{params.dataset_name}", "", f"**{len(files)} file(s):**"]
        for url in files[:50]:
            lines.append(f"- {url}")
        if len(files) > 50:
            lines.append(f"\n_...showing first 50 of {len(files)}._")
        return "\n".join(lines).rstrip() + "\n"
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool(name="s2_resolve_identifier", annotations={"title": "Resolve paper identifier", **READ_ONLY_ANNOTATIONS})
async def s2_resolve_identifier(params: ResolveIdentifierInput) -> str:
    """Normalise any accepted paper identifier to canonical paperId + externalIds."""
    try:
        data = await client.request("GET", f"/paper/{params.paper_id}", params={"fields": "paperId,title,externalIds"})
        normalised = {"paperId": data.get("paperId"), "title": data.get("title"), "externalIds": data.get("externalIds")}
        if params.response_format is ResponseFormat.JSON:
            return as_json(normalised)
        lines = [f"# Resolved identifier: {params.paper_id}", ""]
        lines.append(f"- **paperId (CorpusId)**: {normalised['paperId']}")
        lines.append(f"- **Title**: {normalised['title']}")
        ext = normalised["externalIds"] or {}
        if ext:
            lines.append("- **externalIds**:")
            for k, v in ext.items():
                lines.append(f"  - {k}: {v}")
        return "\n".join(lines) + "\n"
    except Exception as exc:
        return handle_api_error(exc)


@mcp.resource("s2://paper/{paper_id}")
async def paper_resource(paper_id: str) -> str:
    """Human-readable summary of a paper by identifier."""
    try:
        data = await client.request("GET", f"/paper/{paper_id}", params={"fields": DEFAULT_PAPER_FIELDS})
        return format_paper(data, ResponseFormat.MARKDOWN)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.resource("s2://author/{author_id}")
async def author_resource(author_id: str) -> str:
    """Human-readable author profile by Semantic Scholar author ID."""
    try:
        data = await client.request("GET", f"/author/{author_id}", params={"fields": DEFAULT_AUTHOR_FIELDS})
        return format_author(data, ResponseFormat.MARKDOWN)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.resource("s2://paper/{paper_id}/citations")
async def paper_citations_resource(paper_id: str) -> str:
    """First 50 citing papers for the given paper identifier."""
    try:
        data = await client.request("GET", f"/paper/{paper_id}/citations", params={"limit": 50, "fields": DEFAULT_PAPER_LIST_FIELDS})
        raw = data.get("data", []) or []
        papers = extract_citation_papers(raw)
        envelope = build_offset_page(items=papers, offset=0, limit=50, total=data.get("total"))
        return format_paper_list(papers, fmt=ResponseFormat.MARKDOWN, title=f"First 50 citations of {paper_id}", envelope=envelope)
    except Exception as exc:
        return handle_api_error(exc)


__all__ = ["mcp"]
