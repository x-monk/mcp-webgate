# MCP Xsearch

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-blueviolet)](https://spec.modelcontextprotocol.io/)
[![Latest Release](https://img.shields.io/badge/release-v0.1.8-purple.svg)](https://github.com/annibale-x/mcp-xsearch/releases/tag/v0.1.8)

Denoised web search MCP server with intelligent fetching and context flooding protection.

---

## Why

Standard MCP fetch tools return raw HTML with zero filtering — a single page can consume >100k tokens in one shot. `mcp-xsearch` solves this at the architecture level:

- every page is cleaned with **lxml** (XPath removal of nav/footer/script/aside)
- every result is hard-capped to a configurable character budget
- binary files (`.pdf`, `.zip`, `.docx`, …) are blocked **before** any network request
- the `query` tool **never** returns raw HTML — only structured, denoised text

---

## Tools

### `fetch` — single page retrieval

Retrieves and cleans a single URL.

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

### `query` — full search cycle

Executes one or more search queries in parallel, fetches results, cleans them, and returns structured context.

**Input**
```json
{
  "queries": ["python async httpx tutorial", "httpx asyncio guide", "httpx streaming example"],
  "num_results": 5,
  "lang": "en",
  "backend": "searxng"
}
```

`queries` accepts a single string or a list of strings (up to `max_queries`, default 5). Multiple queries run in parallel and results are merged in round-robin order so no single query dominates. The model is responsible for generating complementary queries — xsearch executes them deterministically.

**Output**
```json
{
  "queries": ["python async httpx tutorial", "httpx asyncio guide", "httpx streaming example"],
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
  "stats": {
    "fetched": 5,
    "failed": 0,
    "gap_filled": 0,
    "total_chars": 18200,
    "per_page_limit": 3200
  }
}
```

`snippet_pool` contains results from the oversampling reserve (search-snippet only, no fetch).

### `xsearch_onboarding` — operational guide

Returns a JSON guide explaining how to use xsearch tools effectively. Call it once at the start of a search session.

```json
{ "tools": {...}, "protections": {...}, "tips": [...] }
```

---

## Installation

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

## Configuration

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

### Config file (`xsearch.toml`)

Place in the working directory or your home directory:

```toml
[server]
max_download_mb = 1        # hard cap on per-page download size
max_result_length = 4000   # cap per single page (fetch tool and per-page ceiling in query)
max_query_budget = 16000   # total char budget for a full query response
                           # per-page limit = min(max_result_length, max_query_budget // num_results)
max_queries = 5            # hard cap on parallel queries per call
search_timeout = 8         # seconds
oversampling_factor = 2    # fetch 2x results to fill gaps
auto_recovery_fetch = false
max_total_results = 20
blocked_domains = ["reddit.com", "pinterest.com"]  # optional blocklist
allowed_domains = []       # optional allowlist — if set, only these domains are fetched

[backends]
default = "searxng"

[backends.searxng]
url = "http://localhost:8080"

[backends.brave]
api_key = "BSA..."

[backends.tavily]
api_key = "tvly-..."
search_depth = "basic"
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XSEARCH_DEFAULT_BACKEND` | `searxng` | Active backend (`searxng`, `brave`, `tavily`) |
| `XSEARCH_SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |
| `XSEARCH_BRAVE_API_KEY` | _(empty)_ | Brave Search API key |
| `XSEARCH_TAVILY_API_KEY` | _(empty)_ | Tavily API key |
| `XSEARCH_MAX_DOWNLOAD_MB` | `1.0` | Per-page download size cap |
| `XSEARCH_MAX_RESULT_LENGTH` | `4000` | Per-result character cap |
| `XSEARCH_SEARCH_TIMEOUT` | `8.0` | Request timeout in seconds |
| `XSEARCH_OVERSAMPLING_FACTOR` | `2` | Search result multiplier |
| `XSEARCH_AUTO_RECOVERY_FETCH` | `false` | Enable gap-filler (Round 2 fetch) |
| `XSEARCH_MAX_TOTAL_RESULTS` | `20` | Global cap per `query` call |
| `XSEARCH_MAX_QUERY_BUDGET` | `16000` | Total char budget for a `query` response |
| `XSEARCH_MAX_QUERIES` | `5` | Max number of parallel queries per `query` call |
| `XSEARCH_EXA_API_KEY` | _(empty)_ | Exa API key |
| `XSEARCH_SERPAPI_API_KEY` | _(empty)_ | SerpAPI key |
| `XSEARCH_SERPAPI_ENGINE` | `google` | SerpAPI engine (`google`, `bing`, …) |
| `XSEARCH_SERPAPI_GL` | `us` | SerpAPI country code |
| `XSEARCH_SERPAPI_HL` | `en` | SerpAPI language |
| `XSEARCH_DEBUG` | `false` | Enable debug logging |
| `XSEARCH_LOG_FILE` | _(empty)_ | Log file path (empty = stderr) |

---

## Backends

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

Exa uses neural (semantic) search by default — it's the primary reason to use it over keyword backends. `use_autoprompt` is always disabled internally because mcp-xsearch handles query expansion itself.

### SerpAPI notes

`engine` selects the underlying search engine (`google`, `bing`, `duckduckgo`, `yandex`, `yahoo`) without any code changes. `gl` (country) and `hl` (language) significantly affect result quality.

---

## Multi-query parallel search

The `query` tool accepts `queries` as a single string or a list of strings. The model calling the tool is responsible for generating complementary queries — xsearch executes them in parallel and merges results in round-robin order.

```json
{
  "queries": ["python asyncio tutorial", "asyncio best practices 2024", "asyncio common pitfalls"],
  "num_results": 5
}
```

The server cap `max_queries` (default 5, configurable) silently truncates longer lists.

---

## Debug mode

When enabled, every tool invocation emits a structured log entry with:
- **`fetch`**: URL, raw KB received, clean KB returned, elapsed ms, success/failed
- **`query`**: query string(s), results requested/fetched/failed/gap-filled, raw MB, clean KB, elapsed ms

```bash
# Log to stderr
export XSEARCH_DEBUG=true

# Log to file
export XSEARCH_DEBUG=true
export XSEARCH_LOG_FILE=/var/log/xsearch.log
```

---

## Gap filler (optional)

When `auto_recovery_fetch = true`, failed fetches are automatically retried using the oversampling reserve pool (Round 2). Disabled by default to keep latency predictable.

```bash
export XSEARCH_AUTO_RECOVERY_FETCH=true
```

---

## Protections summary

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

## License

MIT — see [LICENSE](LICENSE).
