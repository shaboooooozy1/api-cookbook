"""Markdown and JSON formatters for Semantic Scholar responses.

Tools share these helpers so each response shape is rendered consistently
regardless of which endpoint produced it.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Iterable


class ResponseFormat(str, Enum):
    """Output format selector."""

    MARKDOWN = "markdown"
    JSON = "json"


def render(data: Any, fmt: ResponseFormat | str) -> str:
    if isinstance(fmt, str):
        fmt = ResponseFormat(fmt)
    if fmt is ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)
    return _markdown_of(data)


def as_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_paper(paper: dict[str, Any], fmt: ResponseFormat) -> str:
    if fmt is ResponseFormat.JSON:
        return as_json(paper)
    return _paper_markdown(paper)


def format_paper_list(
    papers: list[dict[str, Any]],
    *,
    fmt: ResponseFormat,
    title: str,
    envelope: dict[str, Any] | None = None,
) -> str:
    if fmt is ResponseFormat.JSON:
        payload = dict(envelope or {})
        payload["items"] = papers
        return as_json(payload)
    if not papers:
        return f"# {title}\n\n_No matching papers._"
    lines = [f"# {title}", ""]
    if envelope is not None:
        lines.append(_envelope_summary(envelope, noun="papers"))
        lines.append("")
    for i, paper in enumerate(papers, 1):
        lines.append(f"## {i}. {paper.get('title') or '(untitled)'}")
        lines.extend(_paper_summary_bullets(paper))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _paper_markdown(paper: dict[str, Any]) -> str:
    title = paper.get("title") or "(untitled)"
    lines = [f"# {title}", ""]
    lines.extend(_paper_summary_bullets(paper))
    abstract = paper.get("abstract")
    if abstract:
        lines.append("")
        lines.append("## Abstract")
        lines.append(abstract.strip())
    tldr = (paper.get("tldr") or {}).get("text") if isinstance(paper.get("tldr"), dict) else None
    if tldr:
        lines.append("")
        lines.append("## TL;DR")
        lines.append(tldr.strip())
    return "\n".join(lines).rstrip() + "\n"


def _paper_summary_bullets(paper: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if paper.get("paperId"):
        out.append(f"- **Paper ID**: {paper['paperId']}")
    authors = paper.get("authors") or []
    if authors:
        names = ", ".join(_author_inline(a) for a in authors[:10])
        extra = f" (+{len(authors) - 10} more)" if len(authors) > 10 else ""
        out.append(f"- **Authors**: {names}{extra}")
    if paper.get("year") is not None:
        out.append(f"- **Year**: {paper['year']}")
    if paper.get("venue"):
        out.append(f"- **Venue**: {paper['venue']}")
    if paper.get("publicationDate"):
        out.append(f"- **Published**: {paper['publicationDate']}")
    if paper.get("citationCount") is not None:
        out.append(f"- **Citations**: {paper['citationCount']}")
    if paper.get("referenceCount") is not None:
        out.append(f"- **References**: {paper['referenceCount']}")
    fields = paper.get("fieldsOfStudy")
    if fields:
        out.append(f"- **Fields of study**: {', '.join(fields)}")
    ext = paper.get("externalIds") or {}
    if ext:
        pieces = [f"{k}={v}" for k, v in ext.items() if v]
        if pieces:
            out.append(f"- **External IDs**: {', '.join(pieces)}")
    if paper.get("isOpenAccess"):
        pdf = (paper.get("openAccessPdf") or {}).get("url") if isinstance(paper.get("openAccessPdf"), dict) else None
        out.append(f"- **Open access**: yes" + (f" ({pdf})" if pdf else ""))
    return out


def _author_inline(author: dict[str, Any]) -> str:
    name = author.get("name") or "(unknown)"
    aid = author.get("authorId")
    return f"{name} ({aid})" if aid else name


def format_author(author: dict[str, Any], fmt: ResponseFormat) -> str:
    if fmt is ResponseFormat.JSON:
        return as_json(author)
    lines = [f"# {author.get('name') or '(unknown author)'}", ""]
    if author.get("authorId"):
        lines.append(f"- **Author ID**: {author['authorId']}")
    if author.get("aliases"):
        lines.append(f"- **Aliases**: {', '.join(author['aliases'])}")
    if author.get("affiliations"):
        lines.append(f"- **Affiliations**: {', '.join(author['affiliations'])}")
    if author.get("homepage"):
        lines.append(f"- **Homepage**: {author['homepage']}")
    if author.get("paperCount") is not None:
        lines.append(f"- **Papers**: {author['paperCount']}")
    if author.get("citationCount") is not None:
        lines.append(f"- **Citations**: {author['citationCount']}")
    if author.get("hIndex") is not None:
        lines.append(f"- **h-index**: {author['hIndex']}")
    return "\n".join(lines).rstrip() + "\n"


def format_author_list(
    authors: list[dict[str, Any]],
    *,
    fmt: ResponseFormat,
    title: str,
    envelope: dict[str, Any] | None = None,
) -> str:
    if fmt is ResponseFormat.JSON:
        payload = dict(envelope or {})
        payload["items"] = authors
        return as_json(payload)
    if not authors:
        return f"# {title}\n\n_No matching authors._"
    lines = [f"# {title}", ""]
    if envelope is not None:
        lines.append(_envelope_summary(envelope, noun="authors"))
        lines.append("")
    for i, author in enumerate(authors, 1):
        lines.append(f"## {i}. {author.get('name') or '(unknown)'}")
        if author.get("authorId"):
            lines.append(f"- **Author ID**: {author['authorId']}")
        if author.get("affiliations"):
            lines.append(f"- **Affiliations**: {', '.join(author['affiliations'])}")
        if author.get("paperCount") is not None:
            lines.append(f"- **Papers**: {author['paperCount']}")
        if author.get("citationCount") is not None:
            lines.append(f"- **Citations**: {author['citationCount']}")
        if author.get("hIndex") is not None:
            lines.append(f"- **h-index**: {author['hIndex']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _envelope_summary(envelope: dict[str, Any], *, noun: str) -> str:
    total = envelope.get("total")
    count = envelope.get("count")
    offset = envelope.get("offset")
    has_more = envelope.get("has_more")
    next_offset = envelope.get("next_offset")
    parts: list[str] = []
    if total is not None:
        parts.append(f"{total} total {noun}")
    if count is not None:
        parts.append(f"showing {count}")
    if offset is not None:
        parts.append(f"starting at offset {offset}")
    if has_more:
        parts.append(f"more available (next_offset={next_offset})")
    return " -- ".join(parts) if parts else ""


def extract_citation_papers(raw: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        paper = item.get("citingPaper") or item.get("paper")
        if paper:
            out.append(paper)
    return out


def extract_reference_papers(raw: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        paper = item.get("citedPaper") or item.get("paper")
        if paper:
            out.append(paper)
    return out
