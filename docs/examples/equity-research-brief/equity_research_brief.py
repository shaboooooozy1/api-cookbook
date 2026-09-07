#!/usr/bin/env python3
"""
Equity Research Brief - Generate a structured equity research brief for any
public ticker using Perplexity's Agent API with the built-in ``finance_search``
tool.

The Agent API decides which finance categories to fetch (quotes, financials,
earnings transcripts, peer comparisons, analyst estimates) based on the
prompt. ``finance_search`` returns structured market data; the model then
composes the final brief.

Docs:
- Agent API:        https://docs.perplexity.ai/docs/agent-api/quickstart
- finance_search:   https://docs.perplexity.ai/docs/agent-api/finance-search
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from perplexity import Perplexity


# ---------------------------------------------------------------------------
# Recommended configurations from the finance_search docs.
# Each preset maps to a different latency / cost / quality tradeoff.
# ---------------------------------------------------------------------------
CONFIGS: Dict[str, Dict[str, Any]] = {
    "quote": {
        # Live market data and quotes — fastest, cheapest.
        "model": "perplexity/sonar",
        "max_tokens": 1024,
        "max_steps": 1,
        "tools": [{"type": "finance_search"}],
    },
    "single": {
        # Single-company historical lookups — adds web context.
        "model": "openai/gpt-5.5",
        "max_tokens": 2048,
        "max_steps": 5,
        "reasoning_effort": "low",
        "tools": [
            {"type": "web_search"},
            {"type": "finance_search"},
            {"type": "fetch_url"},
        ],
    },
    "research": {
        # Multi-step financial research — cross-company comparisons.
        "model": "anthropic/claude-opus-4-7",
        "max_tokens": 4096,
        "max_steps": 10,
        "tools": [
            {"type": "web_search"},
            {"type": "finance_search"},
            {"type": "fetch_url"},
        ],
    },
}


SYSTEM_PROMPT = """You are an experienced equity research analyst writing a
concise institutional-grade brief for a portfolio manager. Be specific and
quantitative. When you cite numbers, attribute them to the relevant period
(e.g. "FY2025", "Q3 FY26"). Never invent data: only use figures returned by
finance_search or by the web. If a number is unavailable, say so explicitly.
Format the final output in clean Markdown."""


BRIEF_TEMPLATE = """Produce an equity research brief on {ticker}.

Sections (in this order, all required):

1. **Snapshot** — current price, market cap, P/E, 52-week range. Note the as-of
   timestamp returned by finance_search.
2. **Business overview** — 2-3 sentences on what the company does and its main
   revenue lines.
3. **Financial trajectory** — revenue, gross margin, operating margin, and net
   income for the latest fiscal year and the two prior fiscal years. Comment on
   trend.
4. **Latest earnings** — most recent quarter: revenue and EPS actuals vs.
   consensus, headline drivers, and any guidance changes from management
   commentary.
5. **Peer context** — pick 2 close peers and compare them on revenue growth and
   operating margin for the latest fiscal year.
6. **Risks** — 3 specific, current risks (cite source or earnings transcript).
7. **Bottom line** — 2-sentence verdict, clearly labeled as analytical opinion,
   not a recommendation.

End with a "Sources" section listing the URLs returned in finance_search
results and any web pages used."""


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


def generate_brief(
    client: Perplexity,
    ticker: str,
    config_name: str = "research",
) -> Any:
    """Call the Agent API and return the raw response object."""
    cfg = CONFIGS[config_name]
    request: Dict[str, Any] = {
        "model": cfg["model"],
        "instructions": SYSTEM_PROMPT,
        "input": BRIEF_TEMPLATE.format(ticker=ticker.upper()),
        "tools": cfg["tools"],
        "max_output_tokens": cfg["max_tokens"],
    }
    if "max_steps" in cfg:
        request["max_steps"] = cfg["max_steps"]
    if "reasoning_effort" in cfg:
        request["reasoning"] = {"effort": cfg["reasoning_effort"]}
    return client.responses.create(**request)


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------
def _safe_output_text(response: Any) -> str:
    """Concatenate every assistant text block in the response output.

    The SDK's ``response.output_text`` helper assumes every output item is a
    message with a ``.content`` list, but ``finance_results`` items don't
    have ``.content``. Walk the output list defensively instead.
    """
    chunks: List[str] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None) or (
            item.get("type") if isinstance(item, dict) else None
        )
        if item_type != "message":
            continue
        content = (
            getattr(item, "content", None)
            if not isinstance(item, dict)
            else item.get("content")
        )
        for block in content or []:
            block_type = getattr(block, "type", None) or (
                block.get("type") if isinstance(block, dict) else None
            )
            if block_type != "output_text":
                continue
            text = (
                getattr(block, "text", None)
                if not isinstance(block, dict)
                else block.get("text")
            )
            if text:
                chunks.append(text)
    return "\n\n".join(chunks)


def _collect_finance_results(response: Any) -> List[Dict[str, Any]]:
    """Pull every ``finance_results`` item out of the response output."""
    results: List[Dict[str, Any]] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None) or (
            item.get("type") if isinstance(item, dict) else None
        )
        if item_type != "finance_results":
            continue
        # SDK objects expose `.results`; dicts expose ["results"].
        nested = (
            getattr(item, "results", None)
            if not isinstance(item, dict)
            else item.get("results", [])
        ) or []
        for r in nested:
            results.append(
                r.model_dump() if hasattr(r, "model_dump") else r
            )
    return results


def _collect_sources(finance_results: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for r in finance_results:
        for url in r.get("sources", []) or []:
            if url not in seen:
                seen.append(url)
    return seen


def display(response: Any, format_json: bool = False) -> None:
    """Render the response to stdout."""
    if format_json:
        # The SDK response object is Pydantic-like; fall back gracefully.
        if hasattr(response, "model_dump"):
            print(json.dumps(response.model_dump(), indent=2, default=str))
        else:
            print(json.dumps(response, indent=2, default=str))
        return

    finance_results = _collect_finance_results(response)
    sources = _collect_sources(finance_results)

    text = _safe_output_text(response)
    if text:
        print(text)

    if finance_results:
        categories = sorted(
            {r.get("category", "") for r in finance_results if r.get("category")}
        )
        details = getattr(response.usage, "tool_calls_details", None)
        finance_invocations = 0
        if details is not None:
            fs = (
                details.get("finance_search")
                if isinstance(details, dict)
                else getattr(details, "finance_search", None)
            )
            if fs is not None:
                finance_invocations = (
                    fs.get("invocation", 0)
                    if isinstance(fs, dict)
                    else getattr(fs, "invocation", 0)
                )
        print("\n---")
        print(
            f"finance_search: {finance_invocations} invocation(s) "
            f"across categories [{', '.join(categories)}]"
        )

    if sources:
        print("\nFinance sources:")
        for url in sources:
            print(f"  - {url}")

    cost = getattr(getattr(response, "usage", None), "cost", None)
    if cost is not None:
        if not isinstance(cost, dict):
            cost = cost.model_dump() if hasattr(cost, "model_dump") else {}
        total = cost.get("total_cost")
        currency = cost.get("currency", "USD")
        if total is not None:
            print(f"\nCost: {total:.4f} {currency}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an equity research brief using the Perplexity Agent "
            "API and the finance_search tool."
        )
    )
    parser.add_argument(
        "ticker",
        help="Ticker symbol or company name (e.g. NVDA, 'Microsoft').",
    )
    parser.add_argument(
        "--config",
        choices=sorted(CONFIGS.keys()),
        default="research",
        help=(
            "Tool/model configuration: 'quote' (cheapest, live data only), "
            "'single' (one company + web context), or 'research' (full "
            "multi-step brief, default)."
        ),
    )
    parser.add_argument(
        "--api-key",
        help="Perplexity API key (defaults to PERPLEXITY_API_KEY env var).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw Agent API response as JSON.",
    )
    args = parser.parse_args()

    try:
        client = build_client(args.api_key)
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(
        f"Generating {args.config} brief for {args.ticker.upper()}...",
        file=sys.stderr,
    )
    try:
        response = generate_brief(client, args.ticker, args.config)
    except Exception as err:  # noqa: BLE001
        print(f"Agent API error: {err}", file=sys.stderr)
        return 2

    display(response, format_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
