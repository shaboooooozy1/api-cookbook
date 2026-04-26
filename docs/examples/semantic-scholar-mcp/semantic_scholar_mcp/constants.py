"""Module-level constants for the Semantic Scholar MCP server."""

from __future__ import annotations

# API base URLs
GRAPH_API_BASE = "https://api.semanticscholar.org/graph/v1"
RECS_API_BASE = "https://api.semanticscholar.org/recommendations/v1"
DATASETS_API_BASE = "https://api.semanticscholar.org/datasets/v1"

# Environment variable names
API_KEY_ENV_VAR = "SEMANTIC_SCHOLAR_API_KEY"

# Defaults
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_LIMIT = 20
MAX_SEARCH_LIMIT = 100
MAX_BULK_SEARCH_LIMIT = 1000
MAX_BATCH_SIZE = 500
MAX_RECOMMENDATIONS_LIMIT = 500

# Retry
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 2.0

# Default fields surfaced on paper responses when the caller does not
# specify their own. Kept small for context efficiency.
DEFAULT_PAPER_FIELDS = (
    "paperId,title,abstract,year,authors.name,authors.authorId,"
    "citationCount,referenceCount,venue,publicationDate,fieldsOfStudy,"
    "isOpenAccess,openAccessPdf,tldr,externalIds"
)

# Lean set for citation/reference/search list payloads.
DEFAULT_PAPER_LIST_FIELDS = (
    "paperId,title,year,authors.name,citationCount,venue"
)

DEFAULT_AUTHOR_FIELDS = (
    "authorId,name,aliases,affiliations,homepage,paperCount,citationCount,"
    "hIndex"
)

DEFAULT_AUTHOR_PAPERS_FIELDS = (
    "paperId,title,year,venue,citationCount,authors.name"
)
