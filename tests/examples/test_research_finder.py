"""Tests for ``docs/examples/research-finder/research_finder.py``.

The most interesting bit here is ``research_topic``: it has fallback logic that
tries to split the model's free-text response on a literal ``Sources:`` marker,
and a separate path for when the entire response looks like a list of URLs.
Both deserve coverage.
"""

from __future__ import annotations

import pytest

import research_finder as rf


# ---------------------------------------------------------------------------
# Construction & API key resolution
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_explicit_api_key_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PPLX_API_KEY", raising=False)
        # No prompt file on disk — the example falls back to a default and
        # that should not fail construction.
        assistant = rf.ResearchAssistant(
            api_key="explicit", prompt_file="/nonexistent/path.md"
        )
        assert assistant.api_key == "explicit"

    def test_missing_key_raises(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PPLX_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="API key not found"):
            rf.ResearchAssistant()


# ---------------------------------------------------------------------------
# research_topic — Sonar round-trip with mocks
# ---------------------------------------------------------------------------


class TestResearchTopic:
    @pytest.fixture
    def assistant(self) -> rf.ResearchAssistant:
        return rf.ResearchAssistant(api_key="x")

    def test_empty_query_short_circuits(
        self, assistant: rf.ResearchAssistant, mock_sonar
    ) -> None:
        out = assistant.research_topic("   ")
        assert out["error"].startswith("Input query is empty")
        assert len(mock_sonar.calls) == 0

    def test_uses_structured_citations_when_present(
        self,
        assistant: rf.ResearchAssistant,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        mock_sonar.add_response(
            sonar_response_factory(
                "Quantum entanglement is a phenomenon...",
                citations=[
                    "https://arxiv.org/abs/quant-ph/0001",
                    "https://en.wikipedia.org/wiki/Quantum_entanglement",
                ],
            )
        )
        out = assistant.research_topic("entanglement")
        assert out["sources"] == [
            "https://arxiv.org/abs/quant-ph/0001",
            "https://en.wikipedia.org/wiki/Quantum_entanglement",
        ]
        assert "Quantum entanglement" in out["summary"]

    def test_falls_back_to_text_split_on_sources_marker(
        self,
        assistant: rf.ResearchAssistant,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        # No top-level citations => the example tries to split the body on
        # "Sources:" and treat each non-empty line as a source.
        body = (
            "The capital of France is Paris.\n"
            "Sources:\n"
            "- https://example.com/a\n"
            "- https://example.com/b\n"
        )
        mock_sonar.add_response(sonar_response_factory(body, citations=[]))
        out = assistant.research_topic("capital of france")
        assert out["summary"] == "The capital of France is Paris."
        assert out["sources"] == [
            "https://example.com/a",
            "https://example.com/b",
        ]

    def test_recognises_response_that_is_only_urls(
        self,
        assistant: rf.ResearchAssistant,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        body = "https://example.com/a\nhttps://example.com/b\n"
        mock_sonar.add_response(sonar_response_factory(body, citations=[]))
        out = assistant.research_topic("links")
        assert out["sources"] == [
            "https://example.com/a",
            "https://example.com/b",
        ]

    def test_http_error_returns_error_dict(
        self, assistant: rf.ResearchAssistant, mock_sonar
    ) -> None:
        mock_sonar.add_error(status=429)
        out = assistant.research_topic("anything")
        assert "error" in out
        assert "API request failed" in out["error"]
