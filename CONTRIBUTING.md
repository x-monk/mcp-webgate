# Contributing to mcp-xsearch

## Project overview

`mcp-xsearch` is a denoised web search MCP server written in Python. It exposes two tools to any MCP-compatible host (Claude Code, Zed, Cursor, etc.):

- **`fetch`** — retrieve and clean a single URL
- **`query`** — full search cycle: backend query → oversampling → parallel fetch → lxml cleaning → snippet injection → structured output

The core value proposition is **anti-context-flooding**: every result is truncated, sterilized, and protected by hard caps before it reaches the LLM context window.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| [uv](https://docs.astral.sh/uv/) | latest | Package manager and venv |
| git | any | Version control |

---

## Setup

```bash
git clone https://github.com/annibale-x/mcp-xsearch.git
cd mcp-xsearch
uv sync
```

This creates a `.venv` and installs all dependencies (including dev deps).

---

## Project structure

```
src/mcp_xsearch/
  server.py           MCP entry point, tool registration (FastMCP)
  config.py           Pydantic config, env/toml loading
  tools/
    fetch.py          single-page fetch tool
    query.py          full search cycle tool
  backends/
    base.py           abstract SearchBackend interface
    searxng.py        SearXNG backend
  scraper/
    fetcher.py        httpx concurrent fetcher, UA rotation, streaming size cap
    cleaner.py        lxml XPath pipeline + regex text sterilization
  utils/
    url.py            sanitize_url, dedup, binary extension filter
tests/
  test_cleaner.py
  test_config.py
  test_url.py
scripts/
  robot.py            project automation (test/build/bump/promote/publish)
```

---

## Daily commands

All commands run from the project root.

### Run tests

```bash
uv run pytest
uv run pytest tests/test_cleaner.py -v          # single file
uv run pytest tests/test_cleaner.py::TestCleanHtml -v  # single class
```

Or via robot:

```bash
python scripts/robot.py test
```

### Start the server locally

```bash
uv run mcp-xsearch
```

---

## Configuration

`mcp-xsearch` resolves config in this order: **env vars > `xsearch.toml` > defaults**.

Place `xsearch.toml` in the project root or your home directory:

```toml
[server]
max_download_mb = 1
max_result_length = 4000
search_timeout = 8
oversampling_factor = 2
auto_recovery_fetch = false
max_total_results = 20

[backends]
default = "searxng"

[backends.searxng]
url = "http://localhost:8080"

[backends.brave]
api_key = "BSA..."

[backends.tavily]
api_key = "tvly-..."
```

Equivalent env vars use the `XSEARCH_` prefix:

| Env var | Default |
|---------|---------|
| `XSEARCH_DEFAULT_BACKEND` | `searxng` |
| `XSEARCH_SEARXNG_URL` | `http://localhost:8080` |
| `XSEARCH_BRAVE_API_KEY` | _(empty)_ |
| `XSEARCH_TAVILY_API_KEY` | _(empty)_ |
| `XSEARCH_MAX_DOWNLOAD_MB` | `1.0` |
| `XSEARCH_MAX_RESULT_LENGTH` | `4000` |
| `XSEARCH_SEARCH_TIMEOUT` | `8.0` |
| `XSEARCH_OVERSAMPLING_FACTOR` | `2` |
| `XSEARCH_AUTO_RECOVERY_FETCH` | `false` |
| `XSEARCH_MAX_TOTAL_RESULTS` | `20` |

---

## Anti-flooding protections (do not remove)

These are the **core value** of this project. Never remove or bypass them:

| Risk | Protection | Location |
|------|-----------|---------|
| 2 MB raw HTML page | `max_download_mb` hard cap | `scraper/fetcher.py` |
| Oversized text after cleaning | `max_result_length` hard cap | `tools/query.py`, `tools/fetch.py` |
| Too many results | `max_total_results` global cap | `tools/query.py` |
| Binary files (.pdf, .zip, .docx…) | extension filter before any network call | `utils/url.py` |
| Network hangs | `search_timeout`, connect timeout 5 s | `scraper/fetcher.py` |
| Unicode junk, BiDi attacks | regex sterilization pipeline | `scraper/cleaner.py` |

**Critical:** the fetcher uses `client.stream()` + `aiter_bytes()`. **Do not switch to `client.get()`** — it would buffer the full response and bypass the size cap entirely.

---

## Adding a new backend

1. Create `src/mcp_xsearch/backends/<name>.py`
2. Implement the `SearchBackend` ABC:

```python
from .base import SearchBackend, SearchResult

class MyBackend(SearchBackend):
    async def search(self, query: str, num_results: int, lang: str | None = None) -> list[SearchResult]:
        ...
```

3. Add config keys in `config.py` (new `*Config` model + field on `BackendsConfig`)
4. Wire it into `server.py`'s `_get_backend()` dispatch
5. Add unit tests in `tests/`

---

## Release workflow

### 1. Bump version

```bash
python scripts/robot.py bump           # auto-increments patch: 0.1.0 → 0.1.1
python scripts/robot.py bump 0.2.0     # explicit version
```

This will:
- Update `pyproject.toml` and `src/mcp_xsearch/__init__.py`
- Scaffold a new section in `CHANGELOG.md` if not already present
- Commit with message `chore: bump version to X.Y.Z`

**Edit `CHANGELOG.md`** to fill in the actual changes before promoting.

### 2. Promote to main

```bash
python scripts/robot.py promote
```

This will:
- Merge `dev` → `main` (no-ff)
- Create annotated tag `vX.Y.Z`
- Push `main`, `dev`, and the tag to `origin`
- Check out `dev` again

### 3. Build distribution

```bash
python scripts/robot.py build
```

Produces `dist/*.whl` and `dist/*.tar.gz`.

### 4. Publish

```bash
python scripts/robot.py publish           # → PyPI
python scripts/robot.py publish --test    # → TestPyPI
```

Requires `UV_PUBLISH_TOKEN` env var (or `TWINE_PASSWORD`) set to your API token.

---

## Code style

- Python 3.11+ syntax (`X | Y` unions, `match`, etc.)
- No type: ignore comments unless strictly necessary
- `from __future__ import annotations` at the top of every module
- No docstrings on private helpers; public API gets a one-liner
- Tests use plain `pytest` classes — no fixtures unless shared across multiple tests

---

## Roadmap

See [PLAN.md](../PLAN.md) for the full phased roadmap (Phase 1–4, including planned Rust port).
