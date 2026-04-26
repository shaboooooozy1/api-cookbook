"""Pydantic input models for every Semantic Scholar MCP tool."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import (
    DEFAULT_LIMIT,
    MAX_BATCH_SIZE,
    MAX_BULK_SEARCH_LIMIT,
    MAX_RECOMMENDATIONS_LIMIT,
    MAX_SEARCH_LIMIT,
)
from .formatting import ResponseFormat


class _Base(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class _FormatMixin(_Base):
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human reading, 'json' for machine parsing.",
    )


class SearchPapersInput(_FormatMixin):
    query: str = Field(..., description="Free-text search query.", min_length=1, max_length=500)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max papers to return (1-100).", ge=1, le=MAX_SEARCH_LIMIT)
    offset: int = Field(default=0, description="Pagination offset (0-based).", ge=0)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)
    year: Optional[str] = Field(default=None, description="Year filter (e.g. '2021', '2018-2021', '2018-').", max_length=20)
    venue: Optional[str] = Field(default=None, description="Venue filter.", max_length=200)
    fields_of_study: Optional[str] = Field(default=None, description="Fields-of-study filter.", max_length=200)
    open_access_pdf: bool = Field(default=False, description="Restrict to open-access papers.")


class SearchPapersBulkInput(_FormatMixin):
    query: str = Field(..., description="Free-text search query.", min_length=1, max_length=500)
    token: Optional[str] = Field(default=None, description="Continuation token from previous call.", max_length=200)
    limit: int = Field(default=100, description="Max papers per page (1-1000).", ge=1, le=MAX_BULK_SEARCH_LIMIT)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)
    year: Optional[str] = Field(default=None, description="Year filter.", max_length=20)
    venue: Optional[str] = Field(default=None, description="Venue filter.", max_length=200)
    fields_of_study: Optional[str] = Field(default=None, description="Fields-of-study filter.", max_length=200)
    sort: Optional[str] = Field(default=None, description="Sort key (e.g. 'citationCount:desc').", max_length=50)


class MatchPaperByTitleInput(_FormatMixin):
    title: str = Field(..., description="Full paper title to match.", min_length=3, max_length=500)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class GetPaperInput(_FormatMixin):
    paper_id: str = Field(
        ...,
        description="Paper identifier. Accepts CorpusId, DOI, 'ARXIV:<id>', 'MAG:<id>', 'ACL:<id>', 'PMID:<id>', 'PMCID:<id>', or 'URL:<url>'.",
        min_length=1, max_length=300,
    )
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class PaperPaginatedInput(_FormatMixin):
    paper_id: str = Field(..., description="Paper identifier.", min_length=1, max_length=300)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max results per page (1-100).", ge=1, le=MAX_SEARCH_LIMIT)
    offset: int = Field(default=0, description="Pagination offset.", ge=0)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class BatchGetPapersInput(_FormatMixin):
    paper_ids: List[str] = Field(..., description="List of paper identifiers (max 500).", min_length=1, max_length=MAX_BATCH_SIZE)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)

    @field_validator("paper_ids")
    @classmethod
    def _strip_ids(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("paper_ids must contain at least one non-empty identifier")
        return cleaned


class AutocompletePaperTitleInput(_FormatMixin):
    query: str = Field(..., description="Partial paper title.", min_length=1, max_length=200)


class SearchAuthorsInput(_FormatMixin):
    query: str = Field(..., description="Author name or fragment.", min_length=1, max_length=200)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max authors (1-100).", ge=1, le=MAX_SEARCH_LIMIT)
    offset: int = Field(default=0, description="Pagination offset.", ge=0)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class GetAuthorInput(_FormatMixin):
    author_id: str = Field(..., description="Semantic Scholar author ID.", min_length=1, max_length=50)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class GetAuthorPapersInput(_FormatMixin):
    author_id: str = Field(..., description="Semantic Scholar author ID.", min_length=1, max_length=50)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max papers per page (1-100).", ge=1, le=MAX_SEARCH_LIMIT)
    offset: int = Field(default=0, description="Pagination offset.", ge=0)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class BatchGetAuthorsInput(_FormatMixin):
    author_ids: List[str] = Field(..., description="List of author IDs (max 500).", min_length=1, max_length=MAX_BATCH_SIZE)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)

    @field_validator("author_ids")
    @classmethod
    def _strip_ids(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("author_ids must contain at least one non-empty identifier")
        return cleaned


class RecommendFromPaperInput(_FormatMixin):
    paper_id: str = Field(..., description="Seed paper identifier.", min_length=1, max_length=300)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max recommendations (1-500).", ge=1, le=MAX_RECOMMENDATIONS_LIMIT)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)
    recent_only: bool = Field(default=True, description="Restrict to papers published in the last 60 days.")


class RecommendFromListInput(_FormatMixin):
    positive_paper_ids: List[str] = Field(..., description="Papers you WANT more like.", min_length=1, max_length=MAX_BATCH_SIZE)
    negative_paper_ids: Optional[List[str]] = Field(default=None, description="Papers to AVOID.", max_length=MAX_BATCH_SIZE)
    limit: int = Field(default=DEFAULT_LIMIT, description="Max recommendations (1-500).", ge=1, le=MAX_RECOMMENDATIONS_LIMIT)
    fields: Optional[str] = Field(default=None, description="Comma-separated field list.", max_length=500)


class ListDatasetReleasesInput(_FormatMixin):
    """No parameters other than response_format."""


class GetReleaseDatasetsInput(_FormatMixin):
    release_id: str = Field(..., description="Release identifier (YYYY-MM-DD or 'latest').", min_length=1, max_length=20)


class GetDatasetDownloadLinksInput(_FormatMixin):
    release_id: str = Field(..., description="Release identifier.", min_length=1, max_length=20)
    dataset_name: str = Field(..., description="Dataset name (e.g. 'papers', 'authors', 'citations').", min_length=1, max_length=50)


class ResolveIdentifierInput(_FormatMixin):
    paper_id: str = Field(
        ...,
        description="Any accepted Semantic Scholar paper identifier (DOI, ARXIV:<id>, etc.). Returns canonical paperId + externalIds.",
        min_length=1, max_length=300,
    )
