"""Shared fixtures for the api-cookbook test suite.

Each Perplexity example lives in its own directory under ``docs/examples/`` and
is run as a script rather than imported as a package. To exercise them from
tests we add each example directory to ``sys.path`` so the modules can be
imported by name (``import fact_checker`` etc.).

The Sonar API is never hit from tests — every test that exercises a network
path must use the ``mock_sonar`` fixture, which intercepts requests to
``https://api.perplexity.ai`` via the ``responses`` library.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
import responses

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIRS = [
    REPO_ROOT / "docs" / "examples" / "fact-checker-cli",
    REPO_ROOT / "docs" / "examples" / "financial-news-tracker",
    REPO_ROOT / "docs" / "examples" / "daily-knowledge-bot",
    REPO_ROOT / "docs" / "examples" / "research-finder",
]

for path in EXAMPLE_DIRS:
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


# ``newspaper3k`` is a heavyweight dependency that the fact-checker only uses
# in its URL-fetching CLI branch. Tests never exercise that branch, so we stub
# the import to keep the dev requirements small.
if "newspaper" not in sys.modules:
    _newspaper_stub = types.ModuleType("newspaper")

    class _StubArticle:  # pragma: no cover - never instantiated in tests
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.text = ""

        def download(self, *args: Any, **kwargs: Any) -> None: ...
        def parse(self) -> None: ...

    class _StubArticleException(Exception):  # pragma: no cover
        pass

    _newspaper_stub.Article = _StubArticle  # type: ignore[attr-defined]
    _newspaper_stub.ArticleException = _StubArticleException  # type: ignore[attr-defined]
    sys.modules["newspaper"] = _newspaper_stub


SONAR_URL = "https://api.perplexity.ai/chat/completions"


@pytest.fixture(autouse=True)
def _stub_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no test ever picks up a real key from the developer's shell."""
    monkeypatch.setenv("PPLX_API_KEY", "test-key-do-not-use")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key-do-not-use")


def _build_sonar_payload(
    content: str,
    *,
    citations: Optional[List[str]] = None,
    model: str = "sonar-pro",
) -> Dict[str, Any]:
    """Build a Sonar-shaped chat-completion response body."""
    return {
        "id": "chatcmpl-test-0001",
        "model": model,
        "object": "chat.completion",
        "created": 1_700_000_000,
        "citations": citations or [],
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.fixture
def sonar_response_factory() -> Callable[..., Dict[str, Any]]:
    """Factory for canned Sonar response bodies.

    Tests use this to stage a realistic-looking payload whose ``message.content``
    is either free text or a JSON-encoded structured payload, mirroring real
    Sonar behaviour.
    """
    return _build_sonar_payload


@pytest.fixture
def mock_sonar(sonar_response_factory):
    """Intercept POSTs to the Sonar endpoint and serve canned payloads.

    Usage::

        def test_x(mock_sonar, sonar_response_factory):
            mock_sonar.add_response(sonar_response_factory("hello"))
            ...

    The fixture activates ``responses`` for the duration of the test and exposes
    a small helper API. Any unexpected outbound HTTP raises immediately.
    """

    class _Mock:
        def __init__(self) -> None:
            self._rsps = responses.RequestsMock(assert_all_requests_are_fired=False)
            self._rsps.start()

        def add_response(self, body: Dict[str, Any], status: int = 200) -> None:
            self._rsps.add(
                responses.POST,
                SONAR_URL,
                json=body,
                status=status,
            )

        def add_text_response(self, text: str, status: int = 200) -> None:
            self._rsps.add(
                responses.POST,
                SONAR_URL,
                body=text,
                status=status,
                content_type="text/plain",
            )

        def add_error(self, status: int = 500) -> None:
            self._rsps.add(
                responses.POST,
                SONAR_URL,
                json={"error": {"message": "boom"}},
                status=status,
            )

        def add_structured_response(
            self,
            payload: Dict[str, Any],
            *,
            citations: Optional[List[str]] = None,
        ) -> None:
            """Convenience: encode `payload` as JSON inside message.content."""
            body = sonar_response_factory(
                json.dumps(payload), citations=citations
            )
            self.add_response(body)

        @property
        def calls(self):
            return self._rsps.calls

        def stop(self) -> None:
            self._rsps.stop()
            self._rsps.reset()

    mock = _Mock()
    try:
        yield mock
    finally:
        mock.stop()
