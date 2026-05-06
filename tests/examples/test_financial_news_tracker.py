"""Tests for ``docs/examples/financial-news-tracker/financial_news_tracker.py``.

Covers the Pydantic schemas, the time-context helper, the response parser and
the Sonar round trip with the network mocked.
"""

from __future__ import annotations

import json

import pytest

import financial_news_tracker as fnt


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestModels:
    def test_news_item_round_trip(self) -> None:
        item = fnt.NewsItem(
            headline="Apple beats earnings",
            summary="Strong iPhone sales.",
            impact="HIGH",
            sectors_affected=["Technology", "Consumer Electronics"],
            source="Reuters",
        )
        assert item.impact == "HIGH"
        assert item.model_dump()["sectors_affected"][0] == "Technology"

    def test_full_result_validates_nested_payload(self) -> None:
        payload = {
            "query_topic": "tech stocks",
            "time_period": "Last 24 hours",
            "summary": "Mixed day.",
            "news_items": [
                {
                    "headline": "h",
                    "summary": "s",
                    "impact": "LOW",
                    "sectors_affected": [],
                    "source": "AP",
                }
            ],
            "market_analysis": {
                "market_sentiment": "NEUTRAL",
                "key_drivers": ["fed"],
                "risks": ["inflation"],
                "opportunities": ["AI"],
            },
            "recommendations": ["hold"],
        }
        result = fnt.FinancialNewsResult.model_validate(payload)
        assert result.market_analysis.market_sentiment == "NEUTRAL"

    def test_schema_used_for_response_format_is_well_formed(self) -> None:
        schema = fnt.FinancialNewsResult.model_json_schema()
        assert schema["type"] == "object"
        # All top-level fields show up — guards against accidental rename.
        assert {
            "query_topic",
            "time_period",
            "summary",
            "news_items",
            "market_analysis",
            "recommendations",
        } <= set(schema["properties"].keys())


# ---------------------------------------------------------------------------
# _get_time_context
# ---------------------------------------------------------------------------


class TestTimeContext:
    @pytest.fixture
    def tracker(self) -> fnt.FinancialNewsTracker:
        return fnt.FinancialNewsTracker(api_key="x")

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("24h", "Last 24 hours"),
            ("1w", "Last 7 days"),
            ("1m", "Last 30 days"),
            ("3m", "Last 3 months"),
            ("1y", "Last year"),
        ],
    )
    def test_known_ranges(
        self, tracker: fnt.FinancialNewsTracker, given: str, expected: str
    ) -> None:
        assert tracker._get_time_context(given) == expected

    def test_unknown_range_returns_descriptive_fallback(
        self, tracker: fnt.FinancialNewsTracker
    ) -> None:
        assert tracker._get_time_context("5d") == "Recent period (5d)"


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    @pytest.fixture
    def tracker(self) -> fnt.FinancialNewsTracker:
        return fnt.FinancialNewsTracker(api_key="x")

    def test_parses_fenced_json(self, tracker: fnt.FinancialNewsTracker) -> None:
        content = '```json\n{"summary": "ok"}\n```'
        assert tracker._parse_response(content) == {"summary": "ok"}

    def test_falls_back_to_raw_when_no_json(
        self, tracker: fnt.FinancialNewsTracker
    ) -> None:
        out = tracker._parse_response("plain prose, nothing structured")
        assert out == {"raw_response": "plain prose, nothing structured"}


# ---------------------------------------------------------------------------
# get_financial_news with mocked Sonar
# ---------------------------------------------------------------------------


class TestGetFinancialNews:
    @pytest.fixture
    def tracker(self) -> fnt.FinancialNewsTracker:
        return fnt.FinancialNewsTracker(api_key="x")

    def test_empty_query_short_circuits(
        self, tracker: fnt.FinancialNewsTracker, mock_sonar
    ) -> None:
        out = tracker.get_financial_news("   ")
        assert out["error"].startswith("Query is empty")
        assert len(mock_sonar.calls) == 0

    def test_structured_output_includes_schema_and_returns_parsed_payload(
        self, tracker: fnt.FinancialNewsTracker, mock_sonar
    ) -> None:
        payload = {
            "query_topic": "AAPL",
            "time_period": "Last 24 hours",
            "summary": "Stable.",
            "news_items": [],
            "market_analysis": {
                "market_sentiment": "NEUTRAL",
                "key_drivers": [],
                "risks": [],
                "opportunities": [],
            },
            "recommendations": [],
        }
        mock_sonar.add_structured_response(
            payload, citations=["https://reuters.com/a"]
        )

        result = tracker.get_financial_news(
            "AAPL", use_structured_output=True
        )
        assert result["query_topic"] == "AAPL"
        assert result["citations"] == ["https://reuters.com/a"]

        sent = json.loads(mock_sonar.calls[0].request.body)
        assert sent["response_format"]["type"] == "json_schema"
        assert sent["model"] == "sonar-pro"

    def test_structured_output_disabled_for_unsupported_models(
        self, tracker: fnt.FinancialNewsTracker, mock_sonar, sonar_response_factory
    ) -> None:
        # Asking for structured output with an unknown model must not send a
        # response_format block — that's how the example signals "fall back to
        # text parsing".
        mock_sonar.add_response(sonar_response_factory("plain text reply"))
        tracker.get_financial_news(
            "AAPL", model="not-a-real-model", use_structured_output=True
        )
        sent = json.loads(mock_sonar.calls[0].request.body)
        assert "response_format" not in sent

    def test_http_error_returns_error_dict(
        self, tracker: fnt.FinancialNewsTracker, mock_sonar
    ) -> None:
        mock_sonar.add_error(status=500)
        out = tracker.get_financial_news("AAPL")
        assert "error" in out
