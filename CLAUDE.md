# CLAUDE.md

This is the **Perplexity API Cookbook** — a collection of practical examples, integration guides, and community showcases for the [Perplexity Sonar API](https://docs.perplexity.ai/). The repo doubles as the source of truth for `docs.perplexity.ai/cookbook`: every push to `main` triggers a sync workflow that copies `docs/` into the public docs repo.

## Repository Layout

```
api-cookbook/
├── docs/
│   ├── index.mdx              # Cookbook landing page (slug: /)
│   ├── examples/              # Ready-to-run Python apps (one dir per example)
│   ├── articles/              # In-depth integration guides
│   └── showcase/              # Community-built apps (one MDX per project)
├── scripts/validate-mdx.js    # MDX compile check (run in CI)
├── static/                    # Image assets referenced by MDX
├── .github/workflows/
│   ├── pr-validation.yml      # Validates MDX, frontmatter, no localhost links
│   └── sync-to-docs.yml       # Pushes content to ppl-ai/api-docs on main
├── package.json               # Dev-only: @mdx-js/* + glob for validation
├── CONTRIBUTING.md
└── README.md
```

There is no application root — each example/article is self-contained with its own `requirements.txt`. The top-level `package.json` exists solely to install MDX validation tooling for CI.

## Examples (`docs/examples/`)

Each example is a standalone Python project plus a `README.mdx`. Current set:

| Directory | Type | Entry point |
|-----------|------|-------------|
| `fact-checker-cli/` | CLI | `fact_checker.py` |
| `daily-knowledge-bot/` | Scheduled script | `daily_knowledge_bot.py` (+ `.ipynb`) |
| `disease-qa/` | Tutorial / notebook | `disease_qa_tutorial.py` (+ `.ipynb`) |
| `financial-news-tracker/` | CLI | `financial_news_tracker.py` |
| `research-finder/` | CLI | `research_finder.py` |
| `discord-py-bot/` | Discord bot | `bot.py` |

When adding a new example, create a directory under `docs/examples/`, include a `requirements.txt` and a `README.mdx` with the standard frontmatter, and add a section to `docs/examples/README.mdx`.

## Articles (`docs/articles/`)

- `memory-management/` — LlamaIndex-based conversation memory (`chat-summary-memory-buffer/`, `chat-with-persistence/`).
- `openai-agents-integration/` — Using Perplexity through the OpenAI Agents SDK (`pplx_openai.py`).

Articles can have nested subdirectories with their own `README.mdx` and `scripts/`.

## Showcase (`docs/showcase/`)

One MDX file per community project (no code). Each file uses kebab-case naming and has full frontmatter. Showcase content links to external repos rather than hosting them here.

## Claude Code Plugin Integration

Several examples are wired into Claude Code via the **super-app** plugin in `claude-plugins-official`:

- `fact-checker-cli/` → `fact-checker` skill
- `financial-news-tracker/` → `financial-tracker` skill
- `research-finder/` → `research-finder` skill
- `daily-knowledge-bot/` → `knowledge-lookup` skill
- `disease-qa/` → `health-info` skill

Keep example interfaces stable when possible — breaking changes to argv/IO shapes ripple into the plugin.

## Sonar API Conventions

All Python examples follow the same shape:

- **Endpoint:** `https://api.perplexity.ai/chat/completions`
- **Auth:** `Authorization: Bearer $API_KEY` header
- **Models:** `sonar`, `sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`
- **Structured output (Tier 3+):** pass `response_format = {"type": "json_schema", "json_schema": {"schema": MyPydanticModel.model_json_schema()}}`. Define a Pydantic `BaseModel` per response shape (see `fact_checker.py:22-34`, `financial_news_tracker.py:19-43`).
- **Citations:** read from `result["citations"]` and merge with the parsed message content (see `fact_checker.py:150-167`).

### API key environment variable — known inconsistency

The repo is split on naming. **Match the convention of the example you're editing**:

- `PPLX_API_KEY` — `fact-checker-cli`, `financial-news-tracker`, `research-finder`
- `PERPLEXITY_API_KEY` — `daily-knowledge-bot`, `discord-py-bot`, top-level docs

The top-level `README.md` and `docs/examples/README.mdx` advertise `PPLX_API_KEY`. Don't rename across an example without updating its README.

## MDX Authoring Rules (enforced by CI)

`pr-validation.yml` runs on PRs touching `docs/**` and will fail if any of these are violated:

1. **MDX must compile** via `node scripts/validate-mdx.js` (uses `@mdx-js/mdx`).
2. **Every `.mdx` file must start with frontmatter** (`---` markers within first 10 lines). Required fields by convention:
   ```mdx
   ---
   title: ...
   description: ...
   sidebar_position: <number>
   keywords: [comma, separated, tags]
   ---
   ```
3. **No localhost links** (`http://localhost`, `http://127.0.0.1`) anywhere outside `docs/showcase/`.

Run validation locally before pushing:

```bash
npm install
node scripts/validate-mdx.js
```

## Sync Workflow (`sync-to-docs.yml`)

On push to `main`, the contents of `docs/` are copied into `ppl-ai/api-docs` under `cookbook/`, and `static/` is copied into `cookbook/static/`. Navigation is regenerated by a script in the docs repo. **Anything outside `docs/` and `static/` does not ship to the docs site** — keep build scripts, tests, and tooling at the repo root.

## Working in This Repo

- **Don't add Python tooling at the repo root.** Each example owns its own `requirements.txt`; there is no shared virtualenv or top-level `pyproject.toml`.
- **Don't commit secrets.** Examples expect API keys via env vars or a `.env` file (gitignored). Some examples support a local key file (e.g. `pplx_api_key`) — these are read but should never be committed.
- **Prefer editing existing examples** to creating parallel ones; novel patterns belong in `docs/articles/`.
- **README.mdx, not README.md**, for content under `docs/` (the sync workflow and validator only handle MDX). The top-level `README.md` and `CONTRIBUTING.md` stay as plain markdown.
- **Showcase entries are content-only** — no code, no requirements.txt; link to an external repo for the implementation.

## Today's Date Anchor

Files in this repo are content rather than time-sensitive code; treat any "as of <date>" claims in MDX as the author's snapshot, not the current date.
