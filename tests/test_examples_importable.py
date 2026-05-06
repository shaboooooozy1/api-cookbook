"""Smoke test: every supported example imports cleanly.

This is a coarse but high-value check — it catches the kind of breakage that
``requirements.txt`` drift introduces (a renamed dependency, a removed symbol,
an import-time SyntaxError) before any user runs the example.

Examples whose import path has unavoidable side effects (live API calls, hard
filesystem writes, mandatory environment variables) are not exercised here.
They are listed explicitly so the skip is intentional rather than accidental.
"""

from __future__ import annotations

import importlib

import pytest


SAFE_EXAMPLE_MODULES = [
    "fact_checker",
    "financial_news_tracker",
    "daily_knowledge_bot",
    "research_finder",
]


@pytest.mark.parametrize("module_name", SAFE_EXAMPLE_MODULES)
def test_example_module_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    # A trivial sanity check that we got a real module back.
    assert hasattr(module, "main"), f"{module_name} missing a main() entry point"
