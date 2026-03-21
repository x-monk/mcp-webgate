# mcp-xsearch — Project Plan

> Denoised web search MCP server with intelligent fetching and context flooding protection.  
> Initial stack: **Python**. Future port: **Rust**.

---

## 1. Rationale and problem it solves

Claude Code (and LLMs in general) can freely call a standard `fetch` tool and retrieve an
entire page with zero controls: no intelligent truncation, no structural cleaning, no token
budget. The result is the context flooding observed in development: a single fetch consumed
>100k tokens in one shot.

`mcp-xsearch` solves this at the architectural level:

- every page is cleaned with lxml (XPath surgical removal of nav/footer/script/aside)
- every result is truncated to a configurable character budget
- the `query` tool never exposes raw HTML: it only returns structured, denoised text
- the oversampling pool guarantees signal density even when sites block the scraper

---

## 2. Repository structure

```
mcp-xsearch/
├── CLAUDE.md                  # persistent context for Claude Code
├── README.md
├── pyproject.toml             # packaging with uv / pip
├── .python-version
│
├── src/
│   └── mcp_xsearch/
│       ├── __init__.py
│       ├── server.py          # MCP entry point, tool registration
│       ├── config.py          # Config dataclass, loading from env/file
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── fetch.py       # tool: fetch single page
│       │   └── query.py       # tool: full search cycle
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── base.py        # abstract SearchBackend
│       │   ├── brave.py
│       │   ├── searxng.py
│       │   └── tavily.py
│       ├── scraper/
│       │   ├── __init__.py
│       │   ├── fetcher.py     # httpx concurrent fetcher, UA rotation
│       │   └── cleaner.py     # lxml pipeline, noise regex, binary filter
│       └── utils/
│           ├── __init__.py
│           └── url.py         # sanitize_url, dedup, bad_ext filter
│
└── tests/
    ├── test_cleaner.py
    ├── test_fetcher.py
    ├── test_backends.py
    └── test_tools.py
```

---

## 3. Exposed tools (MVP)

### `fetch`

Retrieves and cleans a single URL. Designed for direct model use when the target page
is already known.

**Input:**
```json
{
  "url": "https://example.com/article",
  "max_chars": 4000
}
```

**Output:**
```json
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "text": "cleaned and truncated text...",
  "truncated": true,
  "char_count": 4000
}
```

**Built-in protections:**
- binary extension blocking (.pdf, .docx, .zip, etc.) before any network request
- hard cap on `max_chars` (default 4000, globally configurable maximum)
- configurable timeout (default 8s)
- UA rotation across 20 browser agents (see Section 7)
- tracking parameter removal from URL before fetch

---

### `query`

Full search cycle: multi-query generation, oversampling, parallel fetch, lxml cleaning,
snippet injection, structured context assembly.

**Input:**
```json
{
  "query": "search string",
  "num_results": 5,
  "lang": "en",
  "backend": "searxng"
}
```

**Output:**
```json
{
  "query_used": "expanded query string...",
  "sources": [
    {
      "id": 1,
      "title": "...",
      "url": "...",
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
    "failed": 1,
    "gap_filled": 1,
    "total_chars": 18400
  }
}
```

**Internal pipeline:**
1. Query passthrough (MVP) — optional LLM expansion in Phase 2
2. Search on configured backend with oversampling (configurable factor, default 2x)
3. URL deduplication + binary extension filter
4. Parallel fetch with httpx (Round 1: `num_results` candidates)
5. Optional Gap Filler (Round 2: replaces failed pages from the reserve pool)
6. lxml cleaning per page: removal of nav/footer/script/aside/form/iframe
7. Text cleaning: unicode junk, zero-width chars, BiDi overrides, noise lines
8. Dynamic truncation to `max_result_length`
9. Snippet injection for unread pages (oversampling pool)
10. Structured output serialization

---

## 4. Configuration system

Multi-level configuration, resolution order: **env vars > config file > defaults**.

```toml
# xsearch.toml (optional, in home directory or alongside the server)

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
# no api key required

[backends.brave]
api_key = "BSA..."
safesearch = 1

[backends.tavily]
api_key = "tvly-..."
search_depth = "basic"   # or "advanced"
```

Equivalent env vars: `XSEARCH_DEFAULT_BACKEND`, `XSEARCH_BRAVE_API_KEY`,
`XSEARCH_SEARXNG_URL`, `XSEARCH_MAX_RESULT_LENGTH`, etc.

---

## 5. Search backends

### Abstract `SearchBackend` interface

```python
class SearchBackend(ABC):
    async def search(
        self,
        queries: list[str],
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        ...
```

`SearchResult` is a dataclass with: `title`, `url`, `snippet`.

### Planned backends

| Backend | Auth | Notes |
|---------|------|-------|
| **SearXNG** | none | self-hosted, first priority |
| **Brave Search** | API key | high quality, free tier available |
| **Tavily** | API key | AI-oriented, quality snippets |
| *(future)* DuckDuckGo | none | no official API, fragile |
| *(future)* Google PSE | API key | Programmable Search Engine |

---

## 6. Anti-context-flooding protections

These protections are the core value of this project over existing MCP servers:

| Risk | Protection |
|------|-----------|
| 2MB raw HTML page | `max_download_mb` hard cap on download size |
| Expanded text after cleaning | `max_result_length` hard cap on final chars |
| Fetch loop over many pages | `max_total_results` global cap per call |
| Binary files (.pdf, .zip) | extension filter before any network request |
| Network hangs | `search_timeout` configurable, default 8s |
| Unicode junk and BiDi attacks | regex sterilization pipeline |

---

## 7. HTTP client and anti-blocking strategy

### Why httpx

`httpx` is the HTTP client of choice for the entire project (both `fetch` tool and all
search backend calls). Reasons:

- native `asyncio` support — enables true concurrent page fetching via `asyncio.gather`
- connection pooling via `AsyncClient` context manager — efficient for batch requests
- streaming support — allows the `max_download_mb` cap to abort oversized responses
  mid-transfer without downloading the full body
- drop-in `requests`-compatible API — easy to read and maintain
- actively maintained, used in production at scale

### User-Agent rotation

To avoid 403 blocks from anti-bot systems, every request picks a random UA from a
curated list of 20 real browser agents, ported directly from EasySearch v0.3.4.
The list covers Windows/macOS/Linux desktops, iOS/Android mobile, and niche browsers
(Edge, Opera, Vivaldi, Samsung Browser) to produce a realistic distribution.

```python
# src/mcp_xsearch/scraper/fetcher.py

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/117.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Vivaldi/6.6.3271.45",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]
```

Usage in the concurrent fetcher — the `client.stream()` pattern is critical: it allows
aborting the download as soon as `max_download_mb` is exceeded, without buffering the
full response in memory first:

```python
async def _fetch_single(client: httpx.AsyncClient, url: str, max_bytes: int) -> str:
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    async with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        chunks = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")
```

---

## 8. Roadmap by phase

### Phase 1 — Working MVP (Python)

- [ ] Repo structure and `pyproject.toml`
- [ ] `CLAUDE.md` with full context for Claude Code
- [ ] Config system (env + toml)
- [ ] `scraper/cleaner.py` — lxml pipeline ported from EasySearch
- [ ] `scraper/fetcher.py` — httpx concurrent fetcher, UA rotation
- [ ] `utils/url.py` — sanitize, dedup, bad_ext filter
- [ ] `backends/searxng.py` — first backend
- [ ] `tools/fetch.py` — single page MCP tool
- [ ] `tools/query.py` — full cycle without LLM query expansion
- [ ] `server.py` — tool registration, entry point
- [ ] Unit tests for cleaner and fetcher
- [ ] Integration test with local SearXNG

### Phase 2 — Multi-backend and quality

- [ ] `backends/brave.py`
- [ ] `backends/tavily.py`
- [ ] Runtime backend selection (tool parameter or config)
- [ ] Optional LLM query expansion (via Anthropic API or configurable model)
- [ ] Gap Filler (Round 2 fetch)
- [ ] Extended test suite

### Phase 3 — Hardening and distribution

- [ ] PyPI packaging as `mcp-xsearch`
- [ ] Docker image
- [ ] Installation docs for Claude Code / Zed / Cursor
- [ ] Config schema validated with Pydantic

### Phase 4 — Rust port

- [ ] Same tool schema (`fetch` and `query`), same API contract
- [ ] `reqwest` + `tokio` for fetching
- [ ] `scraper` crate for HTML cleaning (or `html5ever`)
- [ ] Equivalent backend trait
- [ ] Standalone binary, zero runtime dependencies
- [ ] Publish on crates.io as `mcp-xsearch`

---

## 9. Features deliberately not ported

| EasySearch feature | Reason for exclusion |
|--------------------|----------------------|
| Auto-translation (`??:en>it`) | Requires LLM in the loop, increases latency |
| Context-aware trigger (`??` empty) | Specific to OWUI chat pipeline |
| Language Anchor | Same as above |
| RAG/retrieval lockdown | Specific to OWUI pipeline |
| Gap Filler | **Included** but disabled by default (latency) |

---

## 10. Claude Code / Zed integration

Configuration in `.mcp.json` or `claude_desktop_config.json`:

```json
{
  "context_servers": {
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
