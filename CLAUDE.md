# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication

Chat in Italian, develop in English.

## Project

Denoised web search MCP server in Python. Exposes three tools: `webgate_fetch` (single page retrieval + cleaning), `webgate_query` (full search cycle with oversampling, parallel fetch, cleaning, reranking, optional LLM summarization), and `webgate_onboarding` (operational guide). Logic ported from EasySearch v0.3.4 (Open WebUI filter).

## Stack

- Python 3.11+, managed with `uv`
- MCP SDK: `mcp` (Anthropic)
- HTTP client: `httpx` (async, concurrent, streaming)
- HTML parsing: `lxml` (XPath surgical cleaning)
- Config: `pydantic` + `tomllib`
- Tests: `pytest`

## Commands

- `uv run mcp-webgate` — start the server
- `uv run pytest` — run full test suite
- `uv run pytest tests/test_cleaner.py -v` — run a single test file
- `uv run pytest tests/test_cleaner.py::test_name -v` — run a single test

## Architecture

```
src/mcp_webgate/
  server.py          — MCP entry point, tool registration
  config.py          — Pydantic config, env/toml loading (env > file > defaults)
  tools/fetch.py     — single page fetch tool
  tools/query.py     — full search cycle tool
  backends/base.py   — abstract SearchBackend interface
  backends/          — searxng, brave, tavily, exa, serpapi
  scraper/fetcher.py — httpx concurrent fetcher, UA rotation, streaming size cap
  scraper/cleaner.py — lxml pipeline, noise regex, unicode sterilization
  llm/client.py      — async OpenAI-compatible chat client (httpx, no SDK)
  llm/expander.py    — query expansion via LLM
  llm/summarizer.py  — Markdown report with citations via LLM
  utils/url.py       — sanitize_url, dedup, binary extension filter
  utils/reranker.py  — BM25 deterministic + optional LLM reranking
  utils/logger.py    — debug logging
```

**Query pipeline:** search backend → URL dedup + binary filter → parallel fetch (Round 1) → optional gap filler (Round 2) → lxml cleaning → text cleaning → truncation → BM25 reranking → optional LLM reranking → optional LLM summarization → structured output.

## Anti-flooding protections (DO NOT remove)

These are the core value proposition of this project:

- `max_download_mb`: hard cap on per-page download size (streaming, never buffered)
- `max_result_length`: hard cap on chars per cleaned page (default 8000)
- `max_query_budget`: total char budget across all sources (default 32000)
- `max_total_results`: hard cap on total results per call
- Binary extension filter runs BEFORE any network request (.pdf, .zip, .docx, etc.)
- `client.stream()` in fetcher.py — **DO NOT switch to `client.get()`**, it would buffer the full response and bypass the size cap entirely
- Unicode/BiDi sterilization pipeline in cleaner

## Reference implementation

Original logic lives in `sample/easysearch.py` (EasySearch v0.3.4, ~46KB).
Key classes to reference when porting: `WebSearchHandler`, `_process_results`, `_clean_with_lxml`.

## Configuration

Config resolution: env vars > `webgate.toml` > defaults.
Env var naming: `WEBGATE_` prefix (e.g., `WEBGATE_DEFAULT_BACKEND`, `WEBGATE_SEARXNG_URL`, `WEBGATE_MAX_RESULT_LENGTH`).

## Commit and Changelog convention

Do NOT add Co-Authored-By tags to commit messages.

Commit messages and CHANGELOG entries follow this format:

```
* YYYY-MM-DD: vX.Y.Z - <Title> (Hannibal)
  * <type>(<scope>): <description>
  * ...
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

Examples:
```
feat(query): add oversampling gap filler
fix(cleaner): resolve BiDi regex false positive
chore(deps): bump mcp to 1.3.0
```

Git commit messages use the same `type(scope): description` format (no version header).
