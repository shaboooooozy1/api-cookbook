"""Tests for ``docs/examples/daily-knowledge-bot/daily_knowledge_bot.py``.

The bot is one of the more behaviour-rich examples: it has its own ``PerplexityClient``,
a ``DailyFactService`` that picks a topic per calendar day and writes the
result to disk, and a ``load_config`` helper that reads from the environment.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

import daily_knowledge_bot as dkb


# ---------------------------------------------------------------------------
# PerplexityClient
# ---------------------------------------------------------------------------


class TestPerplexityClient:
    def test_missing_key_raises_configuration_error(self) -> None:
        with pytest.raises(dkb.ConfigurationError):
            dkb.PerplexityClient("")

    def test_get_fact_returns_assistant_content(
        self, mock_sonar, sonar_response_factory
    ) -> None:
        mock_sonar.add_response(sonar_response_factory("Octopuses have three hearts."))
        client = dkb.PerplexityClient("real-looking-key")
        assert client.get_fact("biology") == "Octopuses have three hearts."

    def test_get_fact_propagates_http_errors(self, mock_sonar) -> None:
        mock_sonar.add_error(status=502)
        client = dkb.PerplexityClient("k")
        with pytest.raises(requests.exceptions.HTTPError):
            client.get_fact("astronomy")

    def test_get_fact_sends_authorization_header(
        self, mock_sonar, sonar_response_factory
    ) -> None:
        mock_sonar.add_response(sonar_response_factory("fact"))
        client = dkb.PerplexityClient("supersecret")
        client.get_fact("history")
        sent = mock_sonar.calls[0].request
        assert sent.headers["Authorization"] == "Bearer supersecret"


# ---------------------------------------------------------------------------
# DailyFactService — topic management & disk output
# ---------------------------------------------------------------------------


class TestDailyFactService:
    @pytest.fixture
    def service(self, tmp_path: Path) -> dkb.DailyFactService:
        client = dkb.PerplexityClient("k")
        return dkb.DailyFactService(client, output_dir=tmp_path)

    def test_default_topics_seeded(self, service: dkb.DailyFactService) -> None:
        assert "astronomy" in service.topics
        assert len(service.topics) >= 5

    def test_load_topics_from_file_overrides_defaults(
        self, service: dkb.DailyFactService, tmp_path: Path
    ) -> None:
        topics_file = tmp_path / "topics.txt"
        topics_file.write_text("alpha\nbeta\n  gamma  \n\n")
        service.load_topics_from_file(topics_file)
        assert service.topics == ["alpha", "beta", "gamma"]

    def test_load_missing_file_keeps_defaults(
        self, service: dkb.DailyFactService, tmp_path: Path
    ) -> None:
        original = list(service.topics)
        service.load_topics_from_file(tmp_path / "missing.txt")
        assert service.topics == original

    def test_load_empty_file_keeps_defaults(
        self, service: dkb.DailyFactService, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty.txt"
        empty.write_text("\n   \n")
        original = list(service.topics)
        service.load_topics_from_file(empty)
        assert service.topics == original

    def test_get_daily_topic_is_deterministic_for_a_given_day(
        self, service: dkb.DailyFactService
    ) -> None:
        service.topics = ["a", "b", "c", "d", "e"]
        with patch.object(dkb, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 7)  # day=7
            first = service.get_daily_topic()
            mock_dt.now.return_value = datetime(2026, 2, 7)  # also day=7
            second = service.get_daily_topic()
        assert first == second

    def test_get_daily_topic_returns_one_of_the_known_topics(
        self, service: dkb.DailyFactService
    ) -> None:
        service.topics = ["only-one"]
        assert service.get_daily_topic() == "only-one"

    def test_get_random_topic_returns_known_topic(
        self, service: dkb.DailyFactService
    ) -> None:
        service.topics = ["alpha", "beta"]
        assert service.get_random_topic() in {"alpha", "beta"}

    def test_get_and_save_writes_dated_file(
        self,
        service: dkb.DailyFactService,
        tmp_path: Path,
        mock_sonar,
        sonar_response_factory,
    ) -> None:
        mock_sonar.add_response(
            sonar_response_factory("Ada Lovelace wrote the first algorithm.")
        )
        result = service.get_and_save_daily_fact()

        assert result["fact"].startswith("Ada Lovelace")
        out_file = Path(result["filename"])
        assert out_file.parent == tmp_path
        assert out_file.exists()
        body = out_file.read_text()
        assert "DAILY FACT" in body
        assert result["topic"] in body
        assert "Ada Lovelace" in body


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PERPLEXITY_API_KEY", "abc")
        monkeypatch.setenv("OUTPUT_DIR", "/tmp/out")
        monkeypatch.setenv("TOPICS_FILE", "/tmp/topics.txt")
        # Skip dotenv side effects so the env wins regardless of what's on disk.
        with patch.object(dkb, "load_dotenv", lambda *a, **k: None):
            cfg = dkb.load_config()
        assert cfg == {
            "api_key": "abc",
            "output_dir": "/tmp/out",
            "topics_file": "/tmp/topics.txt",
        }

    def test_defaults_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.delenv("TOPICS_FILE", raising=False)
        with patch.object(dkb, "load_dotenv", lambda *a, **k: None):
            cfg = dkb.load_config()
        assert cfg["api_key"] is None
        assert cfg["output_dir"] == "./facts"
        assert cfg["topics_file"] == "./topics.txt"
