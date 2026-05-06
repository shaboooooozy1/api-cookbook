"""Tests for ``docs/examples/fact-checker-cli/fact_checker.py``.

Covers the parts that don't require a live API call:

* Pydantic schema shape (``Claim`` and ``FactCheckResult``)
* ``FactChecker._parse_response`` — fenced-JSON parsing and citation fallback
* ``FactChecker._get_api_key`` — env var vs. on-disk key file precedence
* ``FactChecker._load_system_prompt`` — file load + missing-file fallback
* ``FactChecker.check_claim`` end-to-end with the Sonar API mocked
"""

from __future__ import annotations

import json

import pytest

import fact_checker as fc


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestClaimModel:
    def test_minimal_valid_claim_parses(self) -> None:
        claim = fc.Claim(
            claim="The sky is blue.",
            rating="TRUE",
            explanation="Rayleigh scattering.",
            sources=["https://en.wikipedia.org/wiki/Rayleigh_scattering"],
        )
        assert claim.rating == "TRUE"
        assert claim.sources == [
            "https://en.wikipedia.org/wiki/Rayleigh_scattering"
        ]

    def test_missing_required_field_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            fc.Claim(  # type: ignore[call-arg]
                claim="x", rating="TRUE", explanation="y"
            )

    def test_json_schema_is_sent_to_api(self) -> None:
        # The CLI passes ``FactCheckResult.model_json_schema()`` verbatim as the
        # ``response_format`` JSON Schema. If this shape silently drifts the
        # Sonar API will start rejecting requests.
        schema = fc.FactCheckResult.model_json_schema()
        assert schema["type"] == "object"
        assert "claims" in schema["properties"]
        assert "overall_rating" in schema["properties"]


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    @pytest.fixture
    def checker(self, monkeypatch: pytest.MonkeyPatch) -> fc.FactChecker:
        # Avoid touching the filesystem for the system prompt.
        monkeypatch.setattr(
            fc.FactChecker, "_load_system_prompt", lambda self, p: "stub prompt"
        )
        return fc.FactChecker(api_key="x")

    def test_parses_bare_json(self, checker: fc.FactChecker) -> None:
        out = checker._parse_response('{"summary": "ok"}')
        assert out == {"summary": "ok"}

    def test_parses_json_in_fenced_block(self, checker: fc.FactChecker) -> None:
        content = 'Here you go:\n```json\n{"overall_rating": "MIXED"}\n```\n'
        assert checker._parse_response(content) == {"overall_rating": "MIXED"}

    def test_parses_json_in_unlabelled_fence(
        self, checker: fc.FactChecker
    ) -> None:
        content = '```\n{"k": 1}\n```'
        assert checker._parse_response(content) == {"k": 1}

    def test_falls_back_to_raw_response_with_extracted_citations(
        self, checker: fc.FactChecker
    ) -> None:
        content = (
            "The sky is blue per Rayleigh scattering.\n"
            "Sources: https://example.com/a, https://example.com/b\n"
        )
        out = checker._parse_response(content)
        assert "raw_response" in out
        assert out["extracted_citations"] == [
            "https://example.com/a, https://example.com/b"
        ]

    def test_no_citations_marker_returns_placeholder(
        self, checker: fc.FactChecker
    ) -> None:
        out = checker._parse_response("Just prose, no JSON, no Sources line.")
        assert out["extracted_citations"] == "No citations found"


# ---------------------------------------------------------------------------
# _get_api_key
# ---------------------------------------------------------------------------


class TestGetApiKey:
    def test_env_var_takes_precedence(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PPLX_API_KEY", "from-env")
        (tmp_path / "pplx_api_key").write_text("from-file")

        # ``__init__`` calls ``_load_system_prompt`` so stub it.
        monkeypatch.setattr(
            fc.FactChecker, "_load_system_prompt", lambda self, p: "x"
        )
        assert fc.FactChecker().api_key == "from-env"

    def test_falls_back_to_key_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PPLX_API_KEY", raising=False)
        (tmp_path / "pplx_api_key").write_text("from-file\n")
        monkeypatch.setattr(
            fc.FactChecker, "_load_system_prompt", lambda self, p: "x"
        )
        assert fc.FactChecker().api_key == "from-file"

    def test_missing_key_raises(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PPLX_API_KEY", raising=False)
        monkeypatch.setattr(
            fc.FactChecker, "_load_system_prompt", lambda self, p: "x"
        )
        with pytest.raises(ValueError, match="API key not found"):
            fc.FactChecker()


# ---------------------------------------------------------------------------
# _load_system_prompt
# ---------------------------------------------------------------------------


class TestLoadSystemPrompt:
    def test_reads_existing_prompt_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("custom prompt body  \n")
        checker = fc.FactChecker(api_key="x", prompt_file=str(prompt_file))
        assert checker.system_prompt == "custom prompt body"

    def test_missing_prompt_file_falls_back(
        self, tmp_path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Just confirm that a missing file doesn't crash construction. The
        # current implementation prints a warning and leaves system_prompt as
        # ``None`` (the function returns ``None`` on FileNotFoundError); we
        # assert that behaviour explicitly so a future change is intentional.
        checker = fc.FactChecker(
            api_key="x", prompt_file=str(tmp_path / "does-not-exist.md")
        )
        captured = capsys.readouterr()
        assert "Prompt file not found" in captured.err
        assert checker.system_prompt is None


# ---------------------------------------------------------------------------
# check_claim — full Sonar round-trip with the API mocked
# ---------------------------------------------------------------------------


class TestCheckClaim:
    @pytest.fixture
    def checker(self, monkeypatch: pytest.MonkeyPatch) -> fc.FactChecker:
        monkeypatch.setattr(
            fc.FactChecker, "_load_system_prompt", lambda self, p: "system"
        )
        return fc.FactChecker(api_key="x")

    def test_empty_text_short_circuits_without_calling_api(
        self, checker: fc.FactChecker, mock_sonar
    ) -> None:
        result = checker.check_claim("   ")
        assert result == {
            "error": "Input text is empty. Cannot perform fact check."
        }
        assert len(mock_sonar.calls) == 0

    def test_structured_output_path_parses_json_content(
        self, checker: fc.FactChecker, mock_sonar
    ) -> None:
        payload = {
            "overall_rating": "MIXED",
            "summary": "Some claims hold, others don't.",
            "claims": [
                {
                    "claim": "X happened in 1999.",
                    "rating": "TRUE",
                    "explanation": "Confirmed by source A.",
                    "sources": ["[1]"],
                }
            ],
        }
        mock_sonar.add_structured_response(
            payload, citations=["https://example.com/a"]
        )

        result = checker.check_claim(
            "X happened in 1999.", use_structured_output=True
        )
        assert result["overall_rating"] == "MIXED"
        assert result["citations"] == ["https://example.com/a"]
        # Ensure we sent a request_format with the JSON schema.
        sent_body = json.loads(mock_sonar.calls[0].request.body)
        assert sent_body["response_format"]["type"] == "json_schema"

    def test_unstructured_output_extracts_fenced_json(
        self,
        checker: fc.FactChecker,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        content = '```json\n{"overall_rating": "MOSTLY_TRUE"}\n```'
        mock_sonar.add_response(
            sonar_response_factory(content, citations=["https://ex.com/1"])
        )

        result = checker.check_claim("text", use_structured_output=False)
        assert result["overall_rating"] == "MOSTLY_TRUE"
        assert result["citations"] == ["https://ex.com/1"]

    def test_http_error_returns_error_dict(
        self, checker: fc.FactChecker, mock_sonar
    ) -> None:
        mock_sonar.add_error(status=503)
        result = checker.check_claim("text")
        assert "error" in result
        assert "API request failed" in result["error"]

    def test_malformed_structured_json_returns_error_with_raw_response(
        self,
        checker: fc.FactChecker,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        # Sonar occasionally replies with non-JSON even when structured output
        # is requested — the CLI must surface that gracefully.
        mock_sonar.add_response(
            sonar_response_factory("not actually JSON {")
        )
        result = checker.check_claim("text", use_structured_output=True)
        assert "error" in result
        assert result["raw_response"] == "not actually JSON {"
