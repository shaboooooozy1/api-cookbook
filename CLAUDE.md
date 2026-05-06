# CLAUDE.md

This is the **Perplexity API Cookbook** — a collection of practical examples, integration guides, and community showcases for building applications with the [Perplexity Sonar API](https://docs.perplexity.ai/). Content authored here is automatically synced to `docs.perplexity.ai/cookbook` via GitHub Actions on every push to `main`.

## Repository Layout

```
api-cookbook/
├── docs/
│   ├── index.mdx                      # Cookbook landing page
│   ├── examples/                      # Ready-to-run example apps (Python)
│   │   ├── README.mdx                 # Examples overview
│   │   ├── fact-checker-cli/
│   │   ├── daily-knowledge-bot/
│   │   ├── disease-qa/
│   │   ├── financial-news-tracker/
│   │   ├── research-finder/
│   │   └── discord-py-bot/
│   ├── articles/                      # Long-form integration guides
│   │   ├── memory-management/
│   │   │   ├── chat-summary-memory-buffer/
│   │   │   └── chat-with-persistence/
│   │   └── openai-agents-integration/
│   └── showcase/                      # Community-built apps (MDX only, 26+)
├── scripts/
│   └── validate-mdx.js                # Validates every docs/**/*.mdx compiles
├── static/img/                        # Images, GIFs, demo videos
├── .github/
│   ├── workflows/
│   │   ├── pr-validation.yml          # MDX + frontmatter + link checks on PR
│   │   └── sync-to-docs.yml           # Push docs/ → ppl-ai/api-docs on main
│   └── pull_request_template.md
├── CONTRIBUTING.md
├── package.json                       # Holds @mdx-js + glob for validator
└── README.md
```

## Claude Code Integration

Selected examples are wrapped as Claude Code skills/agents through the **super-app** plugin in `claude-plugins-official`:

| Example directory                               | Claude Code skill   |
| ----------------------------------------------- | ------------------- |
| `docs/examples/fact-checker-cli/`               | `fact-checker`      |
| `docs/examples/financial-news-tracker/`         | `financial-tracker` |
| `docs/examples/research-finder/`                | `research-finder`   |
| `docs/examples/daily-knowledge-bot/`            | `knowledge-lookup`  |
| `docs/examples/disease-qa/`                     | `health-info`       |

When updating these examples, keep the public CLI surface (flags, env vars, default model) stable — the plugin invokes them as black-box CLIs.

## Sonar API Pattern

Most examples share the same shape:

- **Endpoint:** `https://api.perplexity.ai/chat/completions`
- **Auth:** `Authorization: Bearer $API_KEY`
- **Models:** `sonar`, `sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`. Default is usually `sonar-pro`.
- **Structured output:** pass `response_format = {"type": "json_schema", "json_schema": {"schema": <pydantic_model>.model_json_schema()}}`. Only the four models above support it, and it requires Tier 3+ API access — always make this opt-in via a `--structured-output` flag with a non-structured fallback.
- **Citations:** the API returns a top-level `citations` array alongside `choices[0].message.content`. Merge it into the parsed result; don't rely solely on inline `[1]`-style references.
- **Discord example only:** uses the OpenAI SDK pointed at `base_url="https://api.perplexity.ai"` instead of raw `requests`.

### API key conventions (inconsistent — match the surrounding example)

| Example                     | Env var              | Other lookup paths                              |
| --------------------------- | -------------------- | ----------------------------------------------- |
| `fact-checker-cli`          | `PPLX_API_KEY`       | `pplx_api_key`, `.pplx_api_key` (cwd)           |
| `research-finder`           | `PPLX_API_KEY`       | `pplx_api_key`, `.pplx_api_key` (cwd or script dir) |
| `financial-news-tracker`    | `PPLX_API_KEY`       | `pplx_api_key`, `.pplx_api_key` (cwd)           |
| `daily-knowledge-bot`       | `PERPLEXITY_API_KEY` | `.env` via `python-dotenv`                      |
| `disease-qa`                | `PERPLEXITY_API_KEY` | `.env` via `python-dotenv`                      |
| `discord-py-bot`            | `PERPLEXITY_API_KEY` | `.env` via `python-dotenv`                      |

When introducing a *new* example, prefer `PPLX_API_KEY` to match the README and the rest of the cookbook's surface.

## Content Structure & Conventions

### MDX is the source of truth

Every documentation file under `docs/` is `.mdx` (not `.md`) so it can be rendered by the docs site. The PR validation workflow enforces:

1. The file compiles with `@mdx-js/mdx` (no broken JSX, no unclosed components).
2. The first ~10 lines contain a frontmatter block (opening `---`).
3. No `http://localhost` or `http://127.0.0.1` links appear outside `docs/showcase/`.

Required frontmatter fields:

```mdx
---
title: <Human-readable title>
description: <One-sentence description>
sidebar_position: <integer>     # optional but expected
keywords: [tag1, tag2, tag3]
---
```

### Examples (`docs/examples/<name>/`)

Each example directory should contain:

- `README.mdx` — frontmatter + features + install + usage + code walkthrough
- One or more Python entry points (e.g. `<name>.py`)
- `requirements.txt` pinned with `>=` lower bounds
- Optional Jupyter notebook (`.ipynb`) for interactive walk-throughs (see `daily-knowledge-bot`, `disease-qa`)

Examples are **runnable from the directory**: a user is expected to `cd docs/examples/<name>/ && pip install -r requirements.txt && python <name>.py`. Don't introduce package-style imports across example directories.

### Articles (`docs/articles/<topic>/<sub-guide>/`)

Articles are nested two levels deep (topic → guide). Each guide has a `README.mdx` and may include a `scripts/` directory for runnable helpers (see `memory-management/chat-with-persistence/scripts/`).

### Showcase (`docs/showcase/<project>.mdx`)

Showcase entries are a single MDX file each — no code lives in this repo. Code is hosted in the contributor's own repository and linked from the MDX. Localhost links are tolerated here only because some showcase apps describe local-dev setups.

## Development Workflows

### Validating MDX locally

```bash
npm install                      # one-time (installs @mdx-js + glob)
node scripts/validate-mdx.js     # mirrors the PR-validation workflow
```

The validator walks `docs/**/*.mdx`, calls `compile(content, { jsx: true })`, and exits non-zero on the first failure.

### Running an example

```bash
cd docs/examples/<example-name>/
pip install -r requirements.txt
export PPLX_API_KEY=...          # or PERPLEXITY_API_KEY (see table)
python <example-name>.py [args]
```

There is no top-level Python project, no `pyproject.toml`, and no shared virtualenv — keep examples self-contained.

### Sync to docs site

`.github/workflows/sync-to-docs.yml` runs on every push to `main`:

1. Checks out this repo and `ppl-ai/api-docs` (target).
2. Wipes `docs-repo/cookbook/*` and copies `docs/*` into it.
3. Copies `static/*` into `docs-repo/cookbook/static/`.
4. Runs `node scripts/generate-cookbook-nav.js` *in the docs repo* (so navigation is generated downstream — don't add a script of that name here).
5. Commits as `Cookbook Sync Bot` and pushes.

A successful sync writes a commit comment on the source SHA. Failures post a comment too. Do not push files outside `docs/` and `static/` expecting them to appear on the docs site — they won't.

## Conventions for AI Assistants

- **Edit, don't recreate.** This repo is content-heavy; respect existing frontmatter and section ordering. Match the tone of nearby examples.
- **Keep examples runnable.** If you change a CLI flag or env var, update the example's `README.mdx`, the top-level `docs/examples/README.mdx` table, and any reference in this file.
- **Don't invent new top-level directories.** Only `docs/`, `scripts/`, `static/`, and `.github/` are part of the synced surface.
- **No secrets in examples.** Use the env-var/file lookup pattern; never commit a real key. The `.gitignore` already excludes `.env*` files.
- **Showcase additions are MDX-only.** If a contributor PRs runnable code into `docs/showcase/`, redirect them to `docs/examples/` or to host the code in their own repo and link to it.
- **Run `node scripts/validate-mdx.js` before claiming a docs change is complete** — the PR workflow will fail otherwise, and frontmatter mistakes are easy to miss.
- **Don't add `.md` files under `docs/`.** The sync workflow assumes MDX. The one exception is `docs/articles/openai-agents-integration/README.md`, which exists alongside its `README.mdx`; new articles should use MDX only.
