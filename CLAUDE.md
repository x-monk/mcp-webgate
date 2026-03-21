# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Denoised web search MCP server in Python. Exposes two tools: `fetch` (single page retrieval + cleaning) and `query` (full search cycle with oversampling, parallel fetch, cleaning, snippet injection). Logic ported from EasySearch v0.3.4 (Open WebUI filter).

**Status:** Early development — planning docs exist, source code is being built per PLAN.md phases.

## Stack

- Python 3.11+, managed with `uv`
- MCP SDK: `mcp` (Anthropic)
- HTTP client: `httpx` (async, concurrent, streaming)
- HTML parsing: `lxml` (XPath surgical cleaning)
- Config: `pydantic` + `tomllib`
- Tests: `pytest`

## Commands

- `uv run mcp-xsearch` — start the server
- `uv run pytest` — run full test suite
- `uv run pytest tests/test_cleaner.py -v` — run a single test file
- `uv run pytest tests/test_cleaner.py::test_name -v` — run a single test

## Architecture

```
src/mcp_xsearch/
  server.py          — MCP entry point, tool registration
  config.py          — Pydantic config, env/toml loading (env > file > defaults)
  tools/fetch.py     — single page fetch tool
  tools/query.py     — full search cycle tool
  backends/base.py   — abstract SearchBackend interface
  backends/searxng.py — SearXNG backend (priority, self-hosted, no API key)
  scraper/fetcher.py — httpx concurrent fetcher, UA rotation
  scraper/cleaner.py — lxml pipeline, noise regex, unicode sterilization
  utils/url.py       — sanitize_url, dedup, binary extension filter
```

**Query pipeline:** search backend → URL dedup + binary filter → parallel fetch (Round 1) → optional gap filler (Round 2) → lxml cleaning → text cleaning → truncation → snippet injection for unread pages → structured output.

## Anti-flooding protections (DO NOT remove)

These are the core value proposition of this project:

- `max_download_mb`: hard cap on per-page download size
- `max_result_length`: hard cap on chars per result in context
- `max_total_results`: global cap on results per call
- Binary extension filter runs BEFORE any network request (.pdf, .zip, .docx, etc.)
- `client.stream()` in fetcher.py — **DO NOT switch to `client.get()`**, it would buffer the full response and bypass the size cap entirely
- Unicode/BiDi sterilization pipeline in cleaner

## Reference implementation

Original logic lives in `sample/easysearch.py` (EasySearch v0.3.4, ~46KB).
Key classes to reference when porting: `WebSearchHandler`, `_process_results`, `_clean_with_lxml`.

## Configuration

Config resolution: env vars > `xsearch.toml` > defaults.
Env var naming: `XSEARCH_` prefix (e.g., `XSEARCH_DEFAULT_BACKEND`, `XSEARCH_SEARXNG_URL`, `XSEARCH_MAX_RESULT_LENGTH`).
