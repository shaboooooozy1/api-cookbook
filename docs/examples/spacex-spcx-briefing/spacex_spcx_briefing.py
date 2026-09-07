#!/usr/bin/env python3
"""
SpaceX (NASDAQ: SPCX) financial briefing — a single-shot Agent API call that
showcases the ``finance_search`` tool against a newly-listed, segment-heavy
ticker.

Why this example exists
-----------------------
Most equity-research walkthroughs hit large-cap, mature tickers where every
field is well-populated. ``finance_search`` is more interesting on a fresh
listing: SpaceX filed its S-1 in May 2026 and ``finance_search`` picks up the
filing data — segment revenue (Connectivity / Space / AI), Starlink subscriber
KPIs, satellites in orbit, total backlog — the moment Perplexity's finance
data provider flips the ticker on.

This script issues **one** Agent API call and prints the model's briefing plus
the raw ``finance_results`` blocks returned by the tool, so you can see both
the structured output and how the model composed the narrative.

Disambiguation note
-------------------
``SPCX`` is a recycled ticker — historically the "SPAC and New Issue ETF". The
system prompt explicitly tells the model that ``SPCX`` is now Space Exploration
Technologies Corp., and to trust the data returned by ``finance_search``. This
is a useful pattern for any newly-listed company whose ticker was previously
assigned to a different security.

Docs
----
- Agent API:      https://docs.perplexity.ai/docs/agent-api/quickstart
- finance_search: https://docs.perplexity.ai/docs/agent-api/tools/finance-search
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from perplexity import Perplexity


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an equity research analyst writing a concise,
quantitative briefing for a portfolio manager.

CRITICAL TICKER MAPPING: SPCX (NASDAQ: SPCX) is the ticker for Space Exploration
Technologies Corp. (commonly known as SpaceX), which filed its S-1 in May 2026.
The ticker was previously associated with a small SPAC ETF; that mapping is
stale. The finance_search tool returns SpaceX S-1 data under the SPCX symbol —
trust it. If the quote payload shows a legacy "SPAC and New Issue ETF" name,
that is a stale display label only; the underlying segment, KPI, and financial
rows for SPCX are SpaceX's. Do not flag this as a data issue and do not refuse
to write the briefing.

You MUST exercise finance_search multiple times in this run to retrieve quote,
income-statement, segment, and KPI data. A single quote-only fetch is not
acceptable. Use web_search and fetch_url to corroborate any figures against
the SpaceX S-1 filing on SEC EDGAR if needed.

Rules:
- Be quantitative. Attribute every figure to its period (e.g. "FY2025",
  "Q1 2026").
- Use only numbers that come back from finance_search or are corroborated via
  the SEC filing. Never invent numbers. If a field is genuinely unavailable
  after multiple finance_search calls, say so explicitly.
- Format the final output in clean Markdown.
- Close with a "Sources" section listing every URL returned in
  finance_results plus any web URLs you cited."""


USER_PROMPT = """Produce a financial briefing on SPCX (Space Exploration
Technologies Corp.). To do this, you must issue MULTIPLE finance_search calls
so that you retrieve every data area below. A single quote-only fetch is not
sufficient.

Call finance_search for each of these data areas before composing the brief:

- Quote and market cap (live quote)
- Annual income statement for FY2023, FY2024, and FY2025
- Segment breakdown for FY2025 (revenue + adjusted EBITDA by Connectivity,
  Space, AI)
- KPI fields: Starlink subscribers, ARPU, satellites in orbit, total backlog,
  backlog-to-NTM %, Falcon launches, Starship launches, mass to orbit

Then write the briefing in this exact section order:

1. **Snapshot** — latest price, market cap, day range, and the timestamp
   returned by finance_search.
2. **FY2023–FY2025 P&L trajectory** — revenue, gross profit, operating income,
   and net income for each of the three reported years. Comment briefly on the
   margin trend.
3. **Segment mix (FY2025)** — total revenue by segment: Connectivity (Starlink),
   Space (launch services + dev), and Artificial Intelligence. Include each
   segment's adjusted EBITDA if returned.
4. **Starlink (Connectivity) KPIs** — most recent period available. Include
   subscribers, ARPU, satellites in orbit, and consumer vs. enterprise &
   government revenue split.
5. **Capacity & backlog** — total backlog, % of backlog to be recognized over
   the next twelve months, Falcon launches, Starship launches, and mass to
   orbit (metric tons) for the latest reported year.
6. **Bottom line** — 2 sentences. Label this as analytical opinion, not a
   recommendation."""


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------
def build_client(api_key: Optional[str] = None) -> Perplexity:
    """Return an authenticated Perplexity client.

    Looks up the key in this order: explicit argument, ``PERPLEXITY_API_KEY``,
    ``PPLX_API_KEY``, then a ``.pplx_api_key`` / ``pplx_api_key`` file in the
    working directory.
    """
    if not api_key:
        api_key = os.environ.get("PERPLEXITY_API_KEY") or os.environ.get(
            "PPLX_API_KEY"
        )
    if not api_key:
        for candidate in (".pplx_api_key", "pplx_api_key"):
            path = Path(candidate)
            if path.exists():
                api_key = path.read_text().strip()
                break
    if not api_key:
        raise RuntimeError(
            "API key not found. Set PERPLEXITY_API_KEY, pass --api-key, or "
            "create a .pplx_api_key file."
        )
    return Perplexity(api_key=api_key)


# ---------------------------------------------------------------------------
# Agent API call
# ---------------------------------------------------------------------------
def generate_briefing(
    client: Perplexity,
    model: str = "openai/gpt-5.5",
    max_output_tokens: int = 4096,
    max_steps: int = 8,
) -> Any:
    """Issue an ``/v1/agent`` call with finance_search + web tools enabled.

    ``max_steps`` lets the model issue several finance_search invocations
    across the categories (quote, financials, segments, kpis). ``web_search``
    and ``fetch_url`` are included so the model can corroborate figures
    against the S-1 filing on SEC EDGAR when useful.
    """
    return client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=USER_PROMPT,
        tools=[
            {"type": "finance_search"},
            {"type": "web_search"},
            {"type": "fetch_url"},
        ],
        max_output_tokens=max_output_tokens,
        max_steps=max_steps,
    )


# ---------------------------------------------------------------------------
# Response parsing helpers
# ---------------------------------------------------------------------------
def _g(obj: Any, key: str) -> Any:
    """SDK objects and dicts use different access patterns — normalize."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def collect_finance_results(response: Any) -> List[Dict[str, Any]]:
    """Pull every ``finance_results`` entry out of ``response.output``."""
    results: List[Dict[str, Any]] = []
    for item in (_g(response, "output") or []):
        if _g(item, "type") != "finance_results":
            continue
        for r in (_g(item, "results") or []):
            results.append(
                r.model_dump() if hasattr(r, "model_dump") else dict(r)
            )
    return results


def safe_output_text(response: Any) -> str:
    """Concatenate every assistant text block in ``response.output``.

    ``response.output_text`` assumes every output item has a ``.content`` list,
    but ``finance_results`` items don't — walk the output defensively.
    """
    chunks: List[str] = []
    for item in (_g(response, "output") or []):
        if _g(item, "type") != "message":
            continue
        for block in (_g(item, "content") or []):
            if _g(block, "type") == "output_text":
                text = _g(block, "text")
                if text:
                    chunks.append(text)
    return "\n\n".join(chunks)


def collect_sources(finance_results: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for r in finance_results:
        for url in r.get("sources") or []:
            if url not in seen:
                seen.append(url)
    return seen


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def display(response: Any, format_json: bool = False) -> None:
    if format_json:
        if hasattr(response, "model_dump"):
            print(json.dumps(response.model_dump(), indent=2, default=str))
        else:
            print(json.dumps(response, indent=2, default=str))
        return

    finance_results = collect_finance_results(response)
    text = safe_output_text(response)

    if text:
        print(text)

    if finance_results:
        categories = sorted(
            {r.get("category", "") for r in finance_results if r.get("category")}
        )
        print("\n---")
        print(
            f"finance_search returned {len(finance_results)} structured "
            f"block(s) across categories [{', '.join(categories)}]"
        )

    sources = collect_sources(finance_results)
    if sources:
        print("\nFinance sources:")
        for url in sources:
            print(f"  - {url}")

    usage = _g(response, "usage")
    cost = _g(usage, "cost")
    if cost is not None:
        if hasattr(cost, "model_dump"):
            cost = cost.model_dump()
        total = cost.get("total_cost")
        currency = cost.get("currency", "USD")
        if total is not None:
            print(f"\nCost: {total:.4f} {currency}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a single-shot SpaceX (SPCX) financial briefing using "
            "the Perplexity Agent API and the finance_search tool."
        )
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5.5",
        help=(
            "Agent API model. Defaults to openai/gpt-5.5. Try "
            "anthropic/claude-opus-4-7 for a more detailed brief."
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=4096,
        help="Cap on output tokens for the briefing (default: 4096).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Maximum tool-call steps the agent may take (default: 8).",
    )
    parser.add_argument(
        "--api-key",
        help="Perplexity API key (defaults to PERPLEXITY_API_KEY env var).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw Agent API response as JSON instead of prose.",
    )
    args = parser.parse_args()

    try:
        client = build_client(args.api_key)
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(
        f"Generating SPCX briefing with model={args.model}...",
        file=sys.stderr,
    )
    try:
        response = generate_briefing(
            client,
            model=args.model,
            max_output_tokens=args.max_output_tokens,
            max_steps=args.max_steps,
        )
    except Exception as err:  # noqa: BLE001
        print(f"Agent API error: {err}", file=sys.stderr)
        return 2

    display(response, format_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
