# MCP Xsearch

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-blueviolet)](https://spec.modelcontextprotocol.io/)
[![Latest Release](https://img.shields.io/badge/release-v0.1.0-purple.svg)](https://github.com/annibale-x/mcp-xsearch/releases/tag/v0.1.0)

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

Executes a search query, fetches results in parallel, cleans them, and returns structured context.

**Input**
```json
{
  "query": "python async httpx tutorial",
  "num_results": 5,
  "lang": "en",
  "backend": "searxng"
}
```

**Output**
```json
{
  "query_used": "python async httpx tutorial",
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
    "total_chars": 18200
  }
}
```

`snippet_pool` contains results from the oversampling reserve (search-snippet only, no fetch).

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
max_result_length = 4000   # hard cap on chars per result
search_timeout = 8         # seconds
oversampling_factor = 2    # fetch 2x results to fill gaps
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
search_depth = "basic"
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XSEARCH_DEFAULT_BACKEND` | `searxng` | Active backend |
| `XSEARCH_SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |
| `XSEARCH_BRAVE_API_KEY` | _(empty)_ | Brave Search API key |
| `XSEARCH_TAVILY_API_KEY` | _(empty)_ | Tavily API key |
| `XSEARCH_MAX_DOWNLOAD_MB` | `1.0` | Per-page download size cap |
| `XSEARCH_MAX_RESULT_LENGTH` | `4000` | Per-result character cap |
| `XSEARCH_SEARCH_TIMEOUT` | `8.0` | Request timeout in seconds |
| `XSEARCH_OVERSAMPLING_FACTOR` | `2` | Search result multiplier |
| `XSEARCH_AUTO_RECOVERY_FETCH` | `false` | Enable gap-filler (Round 2 fetch) |
| `XSEARCH_MAX_TOTAL_RESULTS` | `20` | Global cap per `query` call |

---

## Backends

| Backend | Auth | Notes |
|---------|------|-------|
| **SearXNG** | none | Self-hosted, recommended |
| **Brave Search** | API key | High quality, [free tier available](https://brave.com/search/api/) |
| **Tavily** | API key | AI-oriented snippets, [free tier available](https://tavily.com/) |

### SearXNG quickstart (Docker)

```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

Then set `XSEARCH_SEARXNG_URL=http://localhost:8080`.

---

## Protections summary

| Risk | Protection |
|------|-----------|
| 2 MB raw HTML page | `max_download_mb` hard download cap |
| Oversized text after cleaning | `max_result_length` hard char cap |
| Too many fetched pages | `max_total_results` global cap |
| Binary files (.pdf, .zip, .docx…) | Extension filter before any network request |
| Hanging connections | `search_timeout` + 5 s connect timeout |
| Unicode junk, BiDi injection | Regex sterilization pipeline |

---

## License

MIT — see [LICENSE](LICENSE).
