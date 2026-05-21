# Test Coverage Analysis & Improvement Proposal

## TL;DR

The repo currently has **zero automated Python test coverage**. CI only validates
MDX/frontmatter — no Python file is exercised by any test runner. This proposal
catalogs the gap and recommends a pragmatic, layered testing strategy targeted
at the highest-value seams in each example.

---

## 1. Current state

### Source code under test
~2,600 lines of Python across 11 files:

| Area | Path | Files | LoC |
|---|---|---|---|
| Examples | `docs/examples/fact-checker-cli/` | `fact_checker.py` | 389 |
| Examples | `docs/examples/daily-knowledge-bot/` | `daily_knowledge_bot.py` | 295 |
| Examples | `docs/examples/disease-qa/` | `disease_qa_tutorial.py` | 669 |
| Examples | `docs/examples/financial-news-tracker/` | `financial_news_tracker.py` | 385 |
| Examples | `docs/examples/research-finder/` | `research_finder.py` | 305 |
| Examples | `docs/examples/discord-py-bot/` | `bot.py` | 180 |
| Articles | `docs/articles/memory-management/chat-summary-memory-buffer/scripts/` | `chat_memory_buffer.py`, `example_usage.py` | 86 |
| Articles | `docs/articles/memory-management/chat-with-persistence/scripts/` | `chat_with_persistence.py`, `example_usage.py` | 125 |
| Articles | `docs/articles/openai-agents-integration/` | `pplx_openai.py` | — |

### What exists for testing
- Test files: **none** (no `test_*.py`, no `tests/`, no `conftest.py`).
- Test framework / runner config: **none** (no `pytest.ini`, no
  `pyproject.toml`, no `setup.cfg`).
- Test deps in any `requirements.txt`: **none** (no pytest, no `responses`,
  no `vcrpy`, no `pytest-mock`).
- CI Python checks: **none**. `.github/workflows/pr-validation.yml` runs
  only `scripts/validate-mdx.js` (MDX syntax + frontmatter); no lint, no
  type-check, no Python test step.

### Code-level testability
- Every example has logic intermixed with a CLI `main()` and module-level
  side effects (env loading, client construction at import time in some
  files). This is workable but limits unit testing of pure functions.
- Several examples already define clean, testable seams that just need
  exercising:
  - Pydantic models — `Claim`, `FactCheckResult` (`fact_checker.py:22-34`),
    schemas in `financial_news_tracker.py`, `research_finder.py`.
  - Response parsers — e.g. `FactChecker._parse_response`
    (`fact_checker.py:178-203`), citation re-mapping in `display_results`
    (`fact_checker.py:226-240`).
  - API-key loaders — `FactChecker._get_api_key`
    (`fact_checker.py:63-82`).
  - System-prompt loaders — `FactChecker._load_system_prompt`
    (`fact_checker.py:84-106`).

---

## 2. Gaps, ordered by risk

### High risk (silent breakage likely; cheap to cover)
1. **Structured-output JSON parsing.** `_parse_response` handles three
   shapes (\`\`\`json fence, generic fence, raw JSON) and a regex fallback.
   None of the branches are exercised; a model output regression would
   ship unnoticed. Same shape exists in `research_finder.py` and
   `financial_news_tracker.py`.
2. **Pydantic schema drift.** If a field is renamed in `Claim` /
   `FactCheckResult`, downstream display code breaks at runtime only.
   Round-trip tests (`model_validate(model_dump())`) and a snapshot of
   `model_json_schema()` would catch this.
3. **Citation index re-mapping.** `display_results` parses `[N]`
   references and indexes into the citation list
   (`fact_checker.py:228-240`). Off-by-one and out-of-range cases are
   plausible and untested.
4. **API-key resolution precedence.** Env var vs. four candidate files
   vs. constructor arg — easy to regress; users hit it first.
5. **HTTP error paths.** `requests.post` failures, non-200 responses,
   non-JSON bodies, missing `choices`/`message` keys are all caught and
   converted to `{"error": ...}` dicts. None verified.

### Medium risk
6. **URL ingestion** in `fact_checker.py:344-365` (newspaper3k +
   requests). Network-dependent today; should be mocked.
7. **Memory-management examples** (`chat_memory_buffer.py`,
   `chat_with_persistence.py`) construct clients at import time
   — refactor for testability and add a smoke test that
   `chat_with_memory()` round-trips a message through a stub client.
8. **Disease-QA pandas pipeline** (669 LoC, the largest file). At
   minimum, lock down the data-shape transformations with golden-file
   tests on small fixtures.
9. **Financial-news date/ticker parsing** in `financial_news_tracker.py`.
10. **Discord bot command dispatch** — currently no separation between
    Discord glue and business logic; refactor before testing.

### Low risk (or out of scope)
11. End-to-end tests against the real Perplexity API — flaky, costs
    money, requires secrets. Keep optional, gated on a `PPLX_API_KEY`
    secret and a `nightly` workflow.
12. Discord live-event tests.

---

## 3. Recommended approach

### Layer 1 — Tooling (one PR)
- Add `pyproject.toml` at repo root with `[tool.pytest.ini_options]`
  setting `testpaths`, `pythonpath`, and a `markers` list (`unit`,
  `integration`, `live`).
- Add `requirements-dev.txt` with `pytest`, `pytest-mock`, `responses`
  (or `respx` if we move to `httpx`), `ruff`, `mypy`.
- Add a `tests/` directory mirroring `docs/examples/<name>/` so each
  example owns its tests (`tests/fact_checker/test_parsing.py`, …).
- Add a `pytest` step to `.github/workflows/pr-validation.yml` that
  installs dev deps and runs `pytest -m "not live"`.
- Add a `ruff check` step (non-blocking initially, then blocking).

### Layer 2 — Unit tests (per-example, in priority order)
Target the seams listed in §2.1–5. Concretely for `fact-checker-cli`:

```
tests/fact_checker/
  test_api_key_resolution.py     # _get_api_key precedence: arg > env > files
  test_prompt_loading.py         # missing file -> default; load on success
  test_response_parsing.py       # ```json fence, generic fence, raw, regex fallback
  test_models.py                 # Claim/FactCheckResult round-trip + schema snapshot
  test_citation_remap.py         # [N] -> URL substitution, OOB, malformed
  test_check_claim_http.py       # responses-mocked: 200, 4xx, 5xx, malformed JSON
```

Mirror this pattern for `research-finder` and `financial-news-tracker`
(highest reuse since they share the same parse/structured-output
shape).

### Layer 3 — Integration tests (mocked HTTP)
- Use `responses` to register fixtures of real Sonar API replies (one
  per example). Store fixtures under
  `tests/fixtures/sonar/<scenario>.json`.
- Each example gets at least one happy-path test that runs `main()`
  with mocked HTTP and asserts on the rendered output.

### Layer 4 — Live smoke tests (optional, gated)
- Marker `@pytest.mark.live` skipped unless `PPLX_API_KEY` is set.
- Run on a manual workflow_dispatch only, not on every PR.

### Layer 5 — Static analysis
- `ruff check` for lint (fast, catches real bugs).
- `mypy --strict` per-example, starting with `fact-checker-cli` since
  it already uses Pydantic + typing throughout.

---

## 4. Suggested first PR (smallest viable slice)

1. Add `pyproject.toml`, `requirements-dev.txt`, `tests/` skeleton.
2. Add `tests/fact_checker/test_response_parsing.py` and
   `test_models.py` — pure-function tests, no HTTP, no env.
3. Wire `pytest -m "not live"` into `pr-validation.yml`.

This proves out the harness with ~50 lines of test code and starts
catching the highest-risk regressions (parser drift, schema drift)
immediately. Subsequent PRs expand horizontally to the other examples
using the same pattern.

---

## 5. Non-goals

- 100% line coverage. The examples are pedagogical; covering the
  argparse glue and printf-style display code adds noise.
- Refactoring examples for "perfect testability" before adding tests.
  Add tests where the seams already exist; refactor only when a seam
  is missing for a high-risk path (e.g. memory-management import-time
  side effects).
- Replacing the MDX validator. Keep it; just add Python on top.
