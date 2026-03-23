# Contributing to mcp-webgate

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

server.json           MCP Registry metadata (version auto-updated by robot.py bump)
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

**Logs:** by default, debug output goes to **stderr**. To redirect to a file, set `WEBGATE_LOG_FILE=/path/to/wg.log` (or use `--log-file`). Enable logging with `WEBGATE_DEBUG=true` (or `--debug`). For deep pipeline inspection, add `WEBGATE_TRACE=true` — this emits per-source timing, raw/clean KB, and adaptive budget breakdown when active.

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

For the complete parameter reference with all env vars, CLI args, and defaults, see [Full Configuration](README.md#full-configuration).

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

## CI / CD

The project uses two GitHub Actions workflows:

### CI — cross-platform tests ([`ci.yml`](.github/workflows/ci.yml))

**Trigger:** `push: tags: v*.*.*` — fires automatically when `robot.py promote` pushes the version tag.

**Matrix:** `ubuntu-latest`, `windows-latest`, `macos-latest`, Python 3.11.
`fail-fast: false` — all three platforms always complete even if one fails.

```bash
uv sync --all-groups   # install all deps including dev
uv run pytest -v       # full test suite (mock-based; no live services needed)
```

Integration tests auto-skip because SearXNG and Ollama are not available in CI.

### Publish — PyPI + MCP Registry ([`publish.yml`](.github/workflows/publish.yml))

**Trigger:** `workflow_dispatch` only — dispatched by `robot.py publish` via `gh workflow run`.

Runs on `ubuntu-latest` against the `main` branch:
1. Installs deps, runs tests, builds the distribution
2. Uploads to PyPI (requires `PYPI_TOKEN` repository secret)
3. Publishes to the MCP Registry via `mcp-publisher` (uses the built-in `GITHUB_TOKEN`)

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
- Update version in `pyproject.toml`, `src/mcp_webgate/__init__.py`, and `server.json`
- Update the release badge URL in `README.md`
- Scaffold a CHANGELOG entry if one is not already present
- Commit with `chore: bump version to X.Y.Z`
- **Push `dev` to `origin`** automatically

### 3. Promote to main

```bash
python scripts/robot.py promote          # promote + watch CI
python scripts/robot.py promote --batch  # promote without watching CI
```

`promote` will:
- Run the full test suite and build locally
- Merge `dev` -> `main` (no-ff)
- Create annotated tag `vX.Y.Z`
- Push `main`, `dev`, and the tag to `origin`
- Check out `dev` again
- Watch the CI workflow (`ci.yml`) until it completes (unless `--batch`)

If CI fails, `promote` exits with an error — do not publish until CI is green.

### 4. Publish

```bash
python scripts/robot.py publish
```

`publish` dispatches the GitHub Actions `publish.yml` workflow via `gh workflow run`. The workflow:
- Checks out `main`
- Builds the distribution (`uv build`)
- Uploads to **PyPI** (via twine)
- Publishes to the **MCP Registry** (via `mcp-publisher`)

Wait for CI to pass before running `publish`. Requires:
- `PYPI_TOKEN` secret configured in the GitHub repository
- `GITHUB_TOKEN` (built-in) for MCP Registry authentication

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
