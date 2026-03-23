# Contributing to mcp-webgate

---

## Table of Contents

- [Project overview](#project-overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Project structure](#project-structure)
- [Daily commands](#daily-commands)
- [Configuration](#configuration)
- [LLM features](#llm-features)
- [Anti-flooding protections](#anti-flooding-protections)
- [Adding a new backend](#adding-a-new-backend)
- [Testing](#testing)
- [CI](#ci)
- [Release workflow](#release-workflow)
- [Code style](#code-style)
- [Roadmap](#roadmap)

---

## Project overview

`mcp-webgate` is a denoised web search MCP server written in Python. It exposes three tools to any MCP-compatible host (Claude Code, Zed, Cursor, etc.):

- **`webgate_fetch`** — retrieve and clean a single URL
- **`webgate_query`** — full search cycle: backend query -> oversampling -> parallel fetch -> lxml cleaning -> BM25 reranking -> optional LLM summarization -> structured output
- **`webgate_onboarding`** — returns a JSON operational guide for the calling model

The core value proposition is **anti-context-flooding**: every result is truncated, sterilized, and protected by hard caps before it reaches the LLM context window. An optional LLM layer adds query expansion, summarization, and reranking via any OpenAI-compatible endpoint.

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
git clone https://github.com/annibale-x/mcp-webgate.git
cd mcp-webgate
uv sync
```

This creates a `.venv` and installs all dependencies (including dev deps).

---

## Project structure

```
src/mcp_webgate/
  server.py           MCP entry point, tool registration (FastMCP)
  config.py           Pydantic config: env/toml loading, LLMConfig, field validators
  tools/
    fetch.py          single-page fetch tool
    query.py          full search cycle (reranker + optional summarizer integrated here)
  backends/
    base.py           abstract SearchBackend interface + SearchResult dataclass
    searxng.py        SearXNG backend (no auth required)
    brave.py          Brave Search API backend
    tavily.py         Tavily Search API backend
    exa.py            Exa neural search backend
    serpapi.py        SerpAPI proxy backend (Google, Bing, DuckDuckGo...)
  scraper/
    fetcher.py        httpx concurrent fetcher, UA rotation, streaming size cap, retry backoff
    cleaner.py        lxml XPath pipeline + regex text sterilization + typography normalization
  llm/
    client.py         async OpenAI-compatible /v1/chat/completions client (httpx, no SDK)
    expander.py       single-query -> N complementary queries via LLM
    summarizer.py     Markdown report with inline citations via LLM
  utils/
    url.py            sanitize_url, dedup, binary extension filter, domain allow/blocklist
    logger.py         debug logger setup and structured log helpers
    reranker.py       two-tier reranker: deterministic BM25 + optional LLM-assisted

tests/
  test_cleaner.py
  test_config.py
  test_url.py
  test_fetcher.py
  test_backends.py              Brave, Tavily, Exa, SerpAPI (mocked HTTP)
  test_query.py                 full query pipeline (mocked backends and fetcher)
  test_llm.py                   LLMClient, expander, summarizer, reranker (all mocked)
  test_debug_logger.py          logger setup, log_fetch, log_query, config validators
  test_integration_searxng.py   live SearXNG on localhost:8080 (auto-skip if unavailable)
  test_integration_llm.py       live Ollama on localhost:11434 (auto-skip if unavailable)

scripts/
  robot.py            project automation (test / build / install / bump / promote / publish / status / query)

Dockerfile            multi-stage image with uv, python:3.11-slim, non-root user
```

---

## Daily commands

All commands run from the project root.

### Run tests

```bash
uv run pytest                                          # full suite
uv run pytest tests/test_cleaner.py -v                # single file
uv run pytest tests/test_cleaner.py::TestCleanHtml -v # single class
```

Integration tests auto-skip if the required service is unavailable:

```bash
# requires SearXNG on localhost:8080
uv run pytest tests/test_integration_searxng.py -v

# requires Ollama on localhost:11434
uv run pytest tests/test_integration_llm.py -v
```

Or via robot (runs the full suite including integration tests with auto-skip):

```bash
python scripts/robot.py test
```

### Run a live query

```bash
python scripts/robot.py query "mcp model context protocol"
python scripts/robot.py query "httpx asyncio" --num-results 3 --lang en
python scripts/robot.py query "searxng setup" --backend searxng
```

Loads config from the environment / `webgate.toml`, runs the full search pipeline, and prints the JSON result. Trace mode is always active in robot: when summarization is enabled, both the summary and full source content are included so you can inspect what was fed to the LLM. If summarization fails, `llm_summary_error` shows the reason (e.g. `ReadTimeout`).

You can also enable trace in production via `WEBGATE_TRACE=1` (see env vars below).

### Start the server locally

```bash
uv run mcp-webgate
```

### Project status

```bash
python scripts/robot.py status
```

Prints current branch, version on dev/main, recent changelog entries, and test count.

### Install as uv tool

```bash
python scripts/robot.py install
```

Uninstalls any existing `mcp-webgate` uv tool, clears cached environments, rebuilds the wheel, and installs it fresh. **Close any MCP host (Zed, Claude Desktop, etc.) before running** — the host locks the executable.

---

## Configuration

`mcp-webgate` resolves config in this order: **env vars > `webgate.toml` > defaults**.

`webgate.toml` is looked up at startup: `./webgate.toml` (CWD) -> `~/webgate.toml` (home) -> defaults. Config is read once; changes require a server restart.

Ready-to-use config files are in [`examples/`](examples/).

Place `webgate.toml` in the project root or your home directory:

```toml
[server]
max_download_mb    = 1        # hard cap on per-page download size (MB)
max_result_length  = 8000     # hard char cap per page (no-LLM multi-source queries)
max_query_budget   = 32000    # total char budget for a fetch, or input pool for a query
max_search_queries = 5        # max queries per call (cap on LLM expansion + manual multi-query)
results_per_query  = 5        # results fetched per query; total = results_per_query x num_queries
search_timeout     = 8
oversampling_factor = 2
auto_recovery_fetch = false
max_total_results  = 20       # hard cap on total results regardless of query count
blocked_domains    = []
allowed_domains    = []

[backends]
default = "searxng"

[backends.searxng]
url = "http://localhost:8080"

[backends.brave]
api_key = "BSA..."

[backends.tavily]
api_key = "tvly-..."

[llm]
enabled  = false
base_url = "http://localhost:11434/v1"
api_key  = ""
model    = "llama3.2"
timeout  = 60
expansion_enabled     = true
summarization_enabled = true
llm_rerank_enabled    = false
max_summary_words     = 0     # 0 = derived from max_query_budget / 5
input_budget_factor   = 3     # LLM input total = max_query_budget × factor (default 96k)
```

Full env var reference:

| Env var | Default | Description |
|---------|---------|-------------|
| `WEBGATE_DEFAULT_BACKEND` | `searxng` | Active backend |
| `WEBGATE_SEARXNG_URL` | `http://localhost:8080` | SearXNG URL |
| `WEBGATE_BRAVE_API_KEY` | _(empty)_ | Brave Search API key |
| `WEBGATE_TAVILY_API_KEY` | _(empty)_ | Tavily API key |
| `WEBGATE_EXA_API_KEY` | _(empty)_ | Exa API key |
| `WEBGATE_SERPAPI_API_KEY` | _(empty)_ | SerpAPI key |
| `WEBGATE_SERPAPI_ENGINE` | `google` | SerpAPI engine |
| `WEBGATE_SERPAPI_GL` | `us` | SerpAPI country code |
| `WEBGATE_SERPAPI_HL` | `en` | SerpAPI language |
| `WEBGATE_MAX_DOWNLOAD_MB` | `1` | Per-page download size cap (MB) |
| `WEBGATE_MAX_RESULT_LENGTH` | `8000` | Per-page character cap after cleaning |
| `WEBGATE_MAX_QUERY_BUDGET` | `32000` | Total char budget across all sources in a query |
| `WEBGATE_MAX_SEARCH_QUERIES` | `5` | Max queries per call (expansion + manual) |
| `WEBGATE_RESULTS_PER_QUERY` | `5` | Default results fetched per query |
| `WEBGATE_SEARCH_TIMEOUT` | `8` | Request timeout in seconds |
| `WEBGATE_OVERSAMPLING_FACTOR` | `2` | Search result multiplier |
| `WEBGATE_AUTO_RECOVERY_FETCH` | `false` | Enable gap-filler |
| `WEBGATE_MAX_TOTAL_RESULTS` | `20` | Hard cap on total results per query call |
| `WEBGATE_DEBUG` | `false` | Enable structured debug logging |
| `WEBGATE_LOG_FILE` | _(empty)_ | Log file path (empty = stderr) |
| `WEBGATE_TRACE` | `false` | Include full content in summarized responses (debug) |
| `WEBGATE_LLM_ENABLED` | `false` | Enable LLM features |
| `WEBGATE_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `WEBGATE_LLM_API_KEY` | _(empty)_ | LLM API key (empty for local) |
| `WEBGATE_LLM_MODEL` | `llama3.2` | Model name |
| `WEBGATE_LLM_TIMEOUT` | `15` | LLM request timeout in seconds (60+ for local 27B+ models) |
| `WEBGATE_LLM_EXPANSION_ENABLED` | `true` | Enable automatic query expansion |
| `WEBGATE_LLM_SUMMARIZATION_ENABLED` | `true` | Enable automatic summarization |
| `WEBGATE_LLM_RERANK_ENABLED` | `false` | Enable LLM-assisted reranking |
| `WEBGATE_LLM_MAX_SUMMARY_WORDS` | `0` | Summary word target (0 = max_query_budget / 5) |
| `WEBGATE_LLM_INPUT_BUDGET_FACTOR` | `3` | LLM input budget multiplier (total = max_query_budget × factor) |

---

## LLM features

LLM features are opt-in. When `llm.enabled = false` (the default), the server is fully deterministic. The `[llm]` block activates three capabilities:

### Query expansion (`llm/expander.py`)

When a single query is provided and `expansion_enabled = true`, the server calls the LLM to generate up to `max_search_queries - 1` complementary variants. Falls back to `[query]` on any error.

### Summarization (`llm/summarizer.py`)

Activated automatically when `llm.enabled = true` and `summarization_enabled = true` (both default when LLM is configured). The cleaned source content (total bounded by `max_query_budget × input_budget_factor`, default 96k) is sent to the external LLM, which produces a Markdown report with inline `[N]` citations. The larger input budget (vs the 32k no-LLM cap) is intentional: the LLM compresses the content, so richer input yields a more accurate and complete report.

**Output behavior:**

- **Success:** lean response — `summary` + `citations` only (no raw content, no snippet pool). The invoking model gets maximum information density at minimum context cost.
- **Failure:** `llm_summary_error` contains the actual error reason (e.g. `ReadTimeout`, `HTTPStatusError: 503`) plus full `sources` as fallback, so the invoking model can still work with the cleaned content.

**Report length:** controlled by `max_summary_words`. When `0` (default), derived from `max_query_budget / 5` — with a 32k budget this gives ~6,400 words. The report is a structured reorganization of the search results, not a lossy compression.

**Input budget factor:** `input_budget_factor` (default `3.0`) controls how much content the summarizer receives: `max_query_budget × factor` total (default 96k), distributed across candidates. Higher values give richer summarizer input at the cost of longer LLM calls.

### Reranking (`utils/reranker.py`)

- **Tier 1 — BM25** (always active): deterministic keyword scoring, zero cost
- **Tier 2 — LLM** (opt-in, `llm_rerank_enabled = true`): sends lightweight inputs (title + snippet + 200 chars) to the LLM for semantic scoring; adds latency

The reranker runs *before* the summarizer in the pipeline: `clean -> rerank -> summarize -> output`.

### LLM client (`llm/client.py`)

Async OpenAI-compatible HTTP client built on `httpx` — no SDK dependency. Covers any provider that speaks `/v1/chat/completions`: OpenAI, Ollama, LM Studio, vLLM, Together AI, Groq, and others.

---

## Anti-flooding protections

These are the **core value** of this project. Never remove or bypass them:

| Risk | Protection | Location |
|------|-----------|---------|
| Oversized raw HTML | `max_download_mb` hard cap (streaming, never buffered) | `scraper/fetcher.py` |
| Oversized text after cleaning | `max_result_length` hard char cap per page | `tools/query.py`, `tools/fetch.py` |
| Context saturation from multi-result query | `max_query_budget` total char budget | `tools/query.py` |
| Too many results | `max_total_results` hard cap | `tools/query.py` |
| Binary files (.pdf, .zip, .docx...) | Extension filter before any network call | `utils/url.py` |
| Network hangs | `search_timeout`, 5 s connect timeout | `scraper/fetcher.py` |
| Unicode junk, BiDi attacks | Regex sterilization pipeline | `scraper/cleaner.py` |
| Rate limiting (429/502/503) | Exponential retry backoff, `Retry-After` support | `scraper/fetcher.py` |

**Critical:** the fetcher uses `client.stream()` + `aiter_bytes()`. **Do not switch to `client.get()`** — it buffers the full response and bypasses the size cap entirely.

---

## Adding a new backend

1. Create `src/mcp_webgate/backends/<name>.py`
2. Implement the `SearchBackend` ABC:

```python
from .base import SearchBackend, SearchResult

class MyBackend(SearchBackend):
    async def search(self, query: str, num_results: int, lang: str | None = None) -> list[SearchResult]:
        ...
```

3. Add a `*Config` model in `config.py`, a field on `BackendsConfig`, and entries in `_apply_env`
4. Import and wire it into `server.py`'s `_get_backend()` dispatch
5. Add unit tests in `tests/test_backends.py` (mock HTTP — no real API calls in unit tests)

---

## Testing

- All unit tests are **mock-based** — no live network, no real API keys required
- Integration tests auto-skip when the required service is not reachable
- `tests/test_integration_llm.py` tests against a live Ollama instance (`localhost:11434`)
- Do not add live API calls to unit tests

**Patterns in use:**

```python
# Mock an async context manager (httpx.AsyncClient)
mock_instance = MagicMock()
mock_instance.post = AsyncMock(return_value=mock_response)
with patch("httpx.AsyncClient") as MockClient:
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
    ...

# Mock a backend search call
mock_backend = AsyncMock()
mock_backend.search = AsyncMock(return_value=[SearchResult(...)])
```

Response objects should be `MagicMock()`, not `AsyncMock()` — only the methods that are actually awaited (`aclose`, `send`, `post`) should be `AsyncMock`. This avoids Python 3.11 `AsyncMock._execute_mock_call` ghost-coroutine warnings.

---

## CI

The project uses GitHub Actions to run the full test suite on Windows, Linux, and macOS on every release.

**Trigger:** `push: tags: v*.*.*` — fires automatically when `robot.py promote` pushes the version tag to origin. The action never fires on `dev` pushes, only on actual releases.

**Workflow file:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

**Matrix:** `ubuntu-latest`, `windows-latest`, `macos-latest`, Python 3.11.
`fail-fast: false` — all three platforms always complete even if one fails.

**What it runs:**

```bash
uv sync --all-groups   # install all deps including dev
uv run pytest -v       # full test suite (mock-based; no live services needed)
```

Integration tests (`test_integration_searxng.py`, `test_integration_llm.py`) auto-skip because the required services (SearXNG, Ollama) are not available in the CI environment.

---

## Release workflow

All release steps go through `robot.py`. The standard flow is:

### 1. Update CHANGELOG

Edit `CHANGELOG.md` and add an entry for the new version at the top (below `# Changelog`):

```
* YYYY-MM-DD: vX.Y.Z - Title (Hannibal)
  * feat(scope): description
  * fix(scope): description
```

### 2. Bump version

```bash
python scripts/robot.py bump           # auto-increments patch: 0.1.0 -> 0.1.1
python scripts/robot.py bump 0.2.0     # explicit version
```

`bump` will:
- Update version in `pyproject.toml` and `src/mcp_webgate/__init__.py`
- Update the release badge URL in `README.md`
- Scaffold a CHANGELOG entry if one is not already present
- Commit with `chore: bump version to X.Y.Z`
- **Push `dev` to `origin`** automatically

### 3. Promote to main

```bash
python scripts/robot.py promote
```

`promote` will:
- Merge `dev` -> `main` (no-ff)
- Create annotated tag `vX.Y.Z`
- Push `main`, `dev`, and the tag to `origin`
- Check out `dev` again

### 4. Build distribution

```bash
python scripts/robot.py build
```

Produces `dist/*.whl` and `dist/*.tar.gz`.

### 5. Publish

```bash
python scripts/robot.py publish           # -> PyPI
python scripts/robot.py publish --test    # -> TestPyPI
```

Requires `UV_PUBLISH_TOKEN` (or `TWINE_PASSWORD`) set to your PyPI API token.

---

## Code style

- Python 3.11+ syntax (`X | Y` unions, etc.)
- `from __future__ import annotations` at the top of every module
- No docstrings on private helpers; public API gets a one-liner
- Tests use plain `pytest` classes — fixtures only when shared across multiple tests
- No `type: ignore` comments unless strictly necessary

---

## Roadmap

See [PLAN.md](PLAN.md) for the full phased roadmap (Phases 1-5, including the planned Rust port).
