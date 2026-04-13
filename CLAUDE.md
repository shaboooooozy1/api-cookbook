# CLAUDE.md

This is the Perplexity API Cookbook — a collection of practical examples for building applications with the Perplexity Sonar API.

## Claude Code Integration

The cookbook's patterns and examples are integrated into Claude Code via the **super-app** plugin in the `claude-plugins-official` repository. The plugin wraps the cookbook's capabilities as Claude Code skills and agents:

- **Fact Checker** (`docs/examples/fact-checker-cli/`) -> `fact-checker` skill
- **Financial News Tracker** (`docs/examples/financial-news-tracker/`) -> `financial-tracker` skill
- **Research Finder** (`docs/examples/research-finder/`) -> `research-finder` skill
- **Daily Knowledge Bot** (`docs/examples/daily-knowledge-bot/`) -> `knowledge-lookup` skill
- **Disease QA** (`docs/examples/disease-qa/`) -> `health-info` skill

## Project Structure

- `docs/examples/` — Ready-to-run Python examples using the Sonar API
- `docs/articles/` — Advanced integration guides (memory management, agents)
- `docs/showcase/` — Community-built applications
- `scripts/` — Build and validation utilities

## API Pattern

All examples use the same core pattern:
- Endpoint: `https://api.perplexity.ai/chat/completions`
- Auth: Bearer token via `PPLX_API_KEY` environment variable
- Models: `sonar`, `sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`
- Structured output via `response_format` with JSON schema
