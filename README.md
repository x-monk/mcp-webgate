# MCP Xsearch

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-blueviolet)](https://spec.modelcontextprotocol.io/)
[![Latest Release](https://img.shields.io/badge/release-v0.1.11-purple.svg)](https://github.com/annibale-x/mcp-xsearch/releases/tag/v0.1.11)

Denoised web search MCP server with intelligent fetching and context flooding protection.

---

## 📋 Table of Contents

- [🌱 Gentle Introduction](#-gentle-introduction)
- [🔧 Tools](#-tools)
- [🤖 LLM Features](#-llm-features)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [🔌 Backends](#-backends)
- [🔍 Multi-query parallel search](#-multi-query-parallel-search)
- [🐛 Debug mode](#-debug-mode)
- [🔄 Gap filler](#-gap-filler)
- [🛡️ Protections summary](#️-protections-summary)
- [📄 License](#-license)

---

## 🌱 Gentle Introduction

### The problem: context flooding

When an LLM uses a standard `fetch` MCP tool to read a web page, it receives the full, raw HTML of that page — scripts, navigation bars, footers, cookie banners, ads, and all. A single news article or documentation page can easily contain **200,000 tokens** of noise. With a single tool call, the model's entire context window can be wiped out, leaving no room for the actual conversation.

This isn't hypothetical. It happens routinely whenever a model decides on its own initiative to fetch a URL: it calls the native fetch tool, the full HTML lands in the context, and suddenly your carefully crafted prompt is gone.

### How mcp-xsearch solves it

`mcp-xsearch` acts as a protective layer between the model and the web. Every page that passes through it is:

1. **Structurally cleaned** with `lxml` — navigation menus, footers, scripts, ads, and sidebars are surgically removed before the text even reaches the model
2. **Hard-capped** — each result is truncated to a configurable character budget; no page can ever consume more than its allotted share of context
3. **Binary-filtered** — PDF, ZIP, DOCX and other non-text files are blocked *before* any network request is made
4. **Unicode-sterilized** — zero-width characters, BiDi overrides, and other invisible junk are stripped from the output

The result is that a `query` call returning 5 results will consume a *predictable*, *bounded* amount of context — typically 16,000–20,000 characters total — regardless of how bloated the original pages were.

### The summarization advantage

The LLM features (optional, Phase 4) take this a step further. Instead of returning cleaned text directly to the model, you can route it through a **secondary LLM** that produces a concise summary with inline citations.

This is particularly powerful when using a **self-hosted model** (e.g. Ollama with Llama 3, Gemma 3, Mistral, etc.) because:

- **The secondary model receives generous input** — up to 32,000 characters of rich, clean content per query — so it has the full picture to summarize from
- **The invoking model receives only the summary** — typically a few hundred words with `[1][2]` citations pointing back to sources — consuming a fraction of the context
- **No API cost** — a self-hosted model summarizes for free; only the final compact output reaches the paid/primary model
- **Higher quality** — summarizing from full content produces far more accurate and complete answers than summarizing from truncated snippets

In other words: the secondary model does the heavy lifting on raw content, and your primary model gets a polished, cited briefing instead of a wall of text.

### The pipeline at a glance

```
User query
    ↓
Search backend (SearXNG / Brave / Tavily / Exa / SerpAPI)
    ↓
URL dedup + binary filter + domain filter
    ↓
Parallel fetch (httpx streaming — hard download cap)
    ↓
lxml cleaning (remove nav / footer / scripts / ads)
    ↓
Text sterilization (unicode, BiDi, noise lines)
    ↓
BM25 reranking (deterministic, always active)
    ↓  ← optional LLM reranking
Top-N results
    ↓  ← optional LLM summarization
Structured JSON output → model context
```

---

## 🔧 Tools

### `fetch` — single page retrieval

Retrieves and cleans a single URL. Use this when you already know the URL you need.

**Input**
```json
{
  "url": "https://example.com/article",
  "max_chars": 4000
}
```

**Output**
```json
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "text": "cleaned and truncated text...",
  "truncated": true,
  "char_count": 4000
}
```

---

### `query` — full search cycle

Executes one or more search queries in parallel, fetches results, cleans them, reranks them, and returns structured context. Optionally summarizes via an external LLM.

**Input**
```json
{
  "queries": ["python async httpx tutorial", "httpx asyncio guide"],
  "num_results_per_query": 5,
  "lang": "en",
  "backend": "searxng",
  "summarize": false
}
```

`queries` accepts a single string or a list (up to `max_queries`, default 5). Multiple queries run in parallel and results are merged in round-robin order so no single query dominates. `num_results_per_query` is per query: 3 queries × 5 = 15 total results, bounded by `max_total_results`.

**Output**
```json
{
  "queries": ["python async httpx tutorial", "httpx asyncio guide"],
  "sources": [
    {
      "id": 1,
      "title": "HTTPX Async Client",
      "url": "https://...",
      "snippet": "...",
      "content": "cleaned text...",
      "truncated": false
    }
  ],
  "snippet_pool": [
    { "id": 6, "title": "...", "url": "...", "snippet": "..." }
  ],
  "summary": "Optional Markdown summary with citations [1][2]...",
  "stats": {
    "fetched": 5,
    "failed": 0,
    "gap_filled": 0,
    "total_chars": 18200,
    "per_page_limit": 3200,
    "num_results_per_query": 5
  }
}
```

`snippet_pool` contains results from the oversampling reserve (search-snippet only, not fetched).
`summary` is present only when `summarize=true` and an LLM is configured.

---

### `xsearch_onboarding` — operational guide

Returns a JSON guide explaining how to use xsearch tools effectively. Call it once at the start of a search session. When LLM features are enabled, it reports their status.

```json
{ "tools": {...}, "protections": {...}, "tips": [...], "llm_features": {...} }
```

---

## 🤖 LLM Features

Phase 4 adds optional LLM-assisted intelligence to the pipeline. All features are **opt-in** and require a configured `[llm]` block. The server is fully deterministic when LLM is disabled.

### Configuration

```toml
[llm]
enabled  = true
base_url = "http://localhost:11434/v1"   # Ollama, OpenAI, LM Studio, vLLM, Groq…
api_key  = ""                            # empty for local models
model    = "gemma3:27b"
timeout  = 15.0

# Per-feature flags
expansion_enabled       = true   # auto-expand single queries into N variants
summarization_enabled   = true   # allow summarize=true on query calls
llm_rerank_enabled      = false  # LLM-assisted reranking (adds latency)
summarizer_input_limit  = 32000  # chars of content fed to the summarizer
```

Env vars: `XSEARCH_LLM_ENABLED`, `XSEARCH_LLM_BASE_URL`, `XSEARCH_LLM_API_KEY`, `XSEARCH_LLM_MODEL`, `XSEARCH_LLM_TIMEOUT`.

The `base_url` accepts any OpenAI-compatible endpoint: **OpenAI**, **Ollama**, **LM Studio**, **vLLM**, **Together AI**, **Groq**, and others.

---

### 🔀 Query expansion

When LLM is enabled and `expansion_enabled = true`, a single-query call is automatically expanded into multiple complementary queries before hitting the search backend. If multiple queries are already provided, expansion is skipped.

```
"python asyncio tutorial"
    ↓ expansion (3 queries total)
["python asyncio tutorial", "asyncio event loop deep dive", "asyncio best practices 2024"]
    ↓ all run in parallel
```

Falls back silently to the original query on any LLM error.

---

### 📝 Summarization

When `summarize=true` is passed to the `query` tool and `summarization_enabled = true`:

1. The cleaned content from all fetched sources (up to `summarizer_input_limit` chars, default 32k) is sent to the external LLM
2. The LLM produces a concise Markdown answer with inline citations `[1]`, `[2]`, etc.
3. The `summary` field is appended to the response

**Why the generous input limit matters:** unlike the hard truncation applied to direct output, the summarizer receives the full cleaned content. A 5-source query at 32k input gives the summarizer ~6,400 chars per source to work from — far richer than a truncated snippet. The result is a summary that is both accurate and well-cited.

`max_result_length` controls the *target length* of the summary output (passed as a prompt guideline), not the input fed to the summarizer.

Falls back silently on any LLM error — the rest of the response is always returned.

---

### 🏆 Reranking

Results are reranked before being returned. Two tiers:

**Tier 1 — Deterministic BM25** (always active, zero cost)
Scores each result by keyword overlap between the query and the cleaned text (title + snippet + first 500 chars of content). Improves over raw backend ordering with no network call.

**Tier 2 — LLM-assisted** (opt-in, `llm_rerank_enabled = true`)
Sends the query plus lightweight result summaries (title + snippet + first 200 chars) to the external LLM for semantic relevance judgment. Adds latency proportional to LLM response time.

Pipeline position: `clean → rerank → summarizer (if enabled) → output`.

---

## 📦 Installation

### Via uvx (recommended — no install needed)

```bash
uvx mcp-xsearch
```

### Via pip / uv

```bash
pip install mcp-xsearch
# or
uv add mcp-xsearch
```

---

## ⚙️ Configuration

### Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "xsearch": {
      "command": "uvx",
      "args": ["mcp-xsearch"],
      "env": {
        "XSEARCH_DEFAULT_BACKEND": "searxng",
        "XSEARCH_SEARXNG_URL": "http://localhost:8080",
        "XSEARCH_MAX_RESULT_LENGTH": "4000"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "xsearch": {
      "command": "uvx",
      "args": ["mcp-xsearch"],
      "env": {
        "XSEARCH_DEFAULT_BACKEND": "searxng",
        "XSEARCH_SEARXNG_URL": "http://localhost:8080"
      }
    }
  }
}
```

### With Ollama LLM features

```json
{
  "mcpServers": {
    "xsearch": {
      "command": "uvx",
      "args": ["mcp-xsearch"],
      "env": {
        "XSEARCH_DEFAULT_BACKEND": "searxng",
        "XSEARCH_SEARXNG_URL": "http://localhost:8080",
        "XSEARCH_LLM_ENABLED": "true",
        "XSEARCH_LLM_BASE_URL": "http://localhost:11434/v1",
        "XSEARCH_LLM_MODEL": "gemma3:27b"
      }
    }
  }
}
```

### Config file (`xsearch.toml`)

```toml
[server]
max_download_mb = 1        # hard cap on per-page download size
max_result_length = 4000   # cap per single page / summary output target
max_query_budget = 16000   # total char budget for a full query response
max_queries = 5            # hard cap on parallel queries per call
search_timeout = 8
oversampling_factor = 2
auto_recovery_fetch = false
max_total_results = 20
blocked_domains = ["reddit.com", "pinterest.com"]
allowed_domains = []

[backends]
default = "searxng"

[backends.searxng]
url = "http://localhost:8080"

[backends.brave]
api_key = "BSA..."

[backends.tavily]
api_key = "tvly-..."
search_depth = "basic"

[llm]
enabled  = true
base_url = "http://localhost:11434/v1"
api_key  = ""
model    = "gemma3:27b"
timeout  = 15.0
expansion_enabled      = true
summarization_enabled  = true
llm_rerank_enabled     = false
summarizer_input_limit = 32000
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XSEARCH_DEFAULT_BACKEND` | `searxng` | Active backend |
| `XSEARCH_SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |
| `XSEARCH_BRAVE_API_KEY` | _(empty)_ | Brave Search API key |
| `XSEARCH_TAVILY_API_KEY` | _(empty)_ | Tavily API key |
| `XSEARCH_EXA_API_KEY` | _(empty)_ | Exa API key |
| `XSEARCH_SERPAPI_API_KEY` | _(empty)_ | SerpAPI key |
| `XSEARCH_SERPAPI_ENGINE` | `google` | SerpAPI engine (`google`, `bing`, …) |
| `XSEARCH_SERPAPI_GL` | `us` | SerpAPI country code |
| `XSEARCH_SERPAPI_HL` | `en` | SerpAPI language |
| `XSEARCH_MAX_DOWNLOAD_MB` | `1.0` | Per-page download size cap |
| `XSEARCH_MAX_RESULT_LENGTH` | `4000` | Per-result character cap / summary output target |
| `XSEARCH_MAX_QUERY_BUDGET` | `16000` | Total char budget for a `query` response |
| `XSEARCH_MAX_QUERIES` | `5` | Max parallel queries per `query` call |
| `XSEARCH_SEARCH_TIMEOUT` | `8.0` | Request timeout in seconds |
| `XSEARCH_OVERSAMPLING_FACTOR` | `2` | Search result multiplier |
| `XSEARCH_AUTO_RECOVERY_FETCH` | `false` | Enable gap-filler (Round 2 fetch) |
| `XSEARCH_MAX_TOTAL_RESULTS` | `20` | Global cap per `query` call |
| `XSEARCH_DEBUG` | `false` | Enable debug logging |
| `XSEARCH_LOG_FILE` | _(empty)_ | Log file path (empty = stderr) |
| `XSEARCH_LLM_ENABLED` | `false` | Enable LLM features |
| `XSEARCH_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `XSEARCH_LLM_API_KEY` | _(empty)_ | API key (empty for local models) |
| `XSEARCH_LLM_MODEL` | `llama3.2` | Model name |
| `XSEARCH_LLM_TIMEOUT` | `15.0` | LLM request timeout in seconds |

---

## 🔌 Backends

| Backend | Auth | Notes |
|---------|------|-------|
| **SearXNG** | none | Self-hosted, recommended |
| **Brave Search** | API key | High quality, [free tier available](https://brave.com/search/api/) |
| **Tavily** | API key | AI-oriented snippets, [free tier available](https://tavily.com/) |
| **Exa** | API key | Neural/semantic search, [free tier available](https://exa.ai/) |
| **SerpAPI** | API key | Proxy for Google, Bing, DuckDuckGo and more, [free tier available](https://serpapi.com/) |

### SearXNG quickstart (Docker)

```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

Then set `XSEARCH_SEARXNG_URL=http://localhost:8080`.

### Exa notes

Exa uses neural (semantic) search by default — the primary reason to use it over keyword backends. `use_autoprompt` is always disabled internally because mcp-xsearch handles query expansion.

### SerpAPI notes

`engine` selects the underlying search engine (`google`, `bing`, `duckduckgo`, `yandex`, `yahoo`) without code changes. `gl` and `hl` significantly affect result quality for non-English queries.

---

## 🔍 Multi-query parallel search

The `query` tool accepts `queries` as a single string or a list. The model is responsible for generating complementary queries — xsearch executes them in parallel and merges results in round-robin order.

```json
{
  "queries": ["python asyncio tutorial", "asyncio best practices 2024", "asyncio common pitfalls"],
  "num_results_per_query": 5
}
```

The server cap `max_queries` (default 5) silently truncates longer lists. When LLM is enabled and `expansion_enabled = true`, a single-query call is automatically expanded server-side.

---

## 🐛 Debug mode

When enabled, every tool invocation emits a structured log entry:

- **`fetch`**: URL, raw KB received, clean KB returned, elapsed ms, success/failed
- **`query`**: query string(s), results requested/fetched/failed/gap-filled, raw MB, clean KB, elapsed ms

```bash
export XSEARCH_DEBUG=true             # log to stderr
export XSEARCH_LOG_FILE=/tmp/x.log   # log to file
```

---

## 🔄 Gap filler

When `auto_recovery_fetch = true`, failed fetches are automatically retried using the oversampling reserve pool (Round 2). Disabled by default to keep latency predictable.

```bash
export XSEARCH_AUTO_RECOVERY_FETCH=true
```

---

## 🛡️ Protections summary

| Risk | Protection |
|------|-----------|
| 2 MB raw HTML page | `max_download_mb` hard download cap |
| Oversized text after cleaning | `max_result_length` hard char cap |
| Too many fetched pages | `max_total_results` global cap |
| Context saturation from multi-result query | `max_query_budget` total char budget |
| Binary files (.pdf, .zip, .docx…) | Extension filter before any network request |
| Hanging connections | `search_timeout` + 5 s connect timeout |
| Unicode junk, BiDi injection | Regex sterilization pipeline |
| Blocked by rate limiting (429/502/503) | Exponential retry backoff, respects `Retry-After` |
| Low-quality or unwanted domains | `blocked_domains` / `allowed_domains` filter |

---

## 📄 License

MIT — see [LICENSE](LICENSE).
