# mcp-webgate — Project Plan

> Denoised web search MCP server with intelligent fetching and context flooding protection.  
> Initial stack: **Python**. Future port: **Rust**.

---

## 1. Rationale and problem it solves

Claude Code (and LLMs in general) can freely call a standard `fetch` tool and retrieve an
entire page with zero controls: no intelligent truncation, no structural cleaning, no token
budget. The result is the context flooding observed in development: a single fetch consumed
>100k tokens in one shot.

`mcp-webgate` solves this at the architectural level:

- every page is cleaned with lxml (XPath surgical removal of nav/footer/script/aside)
- every result is truncated to a configurable character budget
- the `query` tool never exposes raw HTML: it only returns structured, denoised text
- the oversampling pool guarantees signal density even when sites block the scraper

---

## 2. Repository structure

```
mcp-webgate/
├── CLAUDE.md                  # persistent context for Claude Code
├── README.md
├── pyproject.toml             # packaging with uv / pip
├── .python-version
│
├── src/
│   └── mcp_webgate/
│       ├── __init__.py
│       ├── server.py          # MCP entry point, tool registration
│       ├── config.py          # Config dataclass, loading from env/file
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── fetch.py       # tool: fetch single page
│       │   ├── query.py       # tool: full search cycle
│       │   └── onboarding.py  # tool: operational guide for models
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── base.py        # abstract SearchBackend
│       │   ├── brave.py
│       │   ├── exa.py
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
  "queries": ["search string", "alternative angle", "specific variant"],
  "num_results": 5,
  "lang": "en",
  "backend": "searxng"
}
```

`queries` accepts a single string or a list (up to `max_queries`, server cap).
Multiple queries run in parallel and results are merged round-robin.

**Output:**
```json
{
  "queries": ["search string", "alternative angle", "specific variant"],
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
1. Accept one or multiple queries from the caller (model handles expansion)
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
# webgate.toml (optional, in home directory or alongside the server)

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

[backends.exa]
api_key = "exa-..."
num_sentences = 3        # snippet length in search results
use_autoprompt = false   # Exa AI query rewriting (skip, we handle it)
type = "neural"          # "neural" (semantic) or "keyword"

[backends.serpapi]
api_key = "serpapi-..."
engine = "google"        # google, bing, duckduckgo, yandex, yahoo
gl = "us"                # country code for results
hl = "en"                # language
safe = "off"             # "active" or "off"
```

Equivalent env vars: `WEBGATE_DEFAULT_BACKEND`, `WEBGATE_BRAVE_API_KEY`,
`WEBGATE_SEARXNG_URL`, `WEBGATE_MAX_RESULT_LENGTH`, etc.

**Note EXA**:
> - `use_autoprompt = false` is important—Exa has its own internal query rewriting, but since mcp-webgate will handle query expansion in Phase 2, it’s better to internally set it disabled to avoid having two layers stepping on each other's toes. Briefly: should not be exposed as user parameter.

> - `type = "neural"` is the default and the primary reason to use Exa—if you just wanted keyword search, you’d use Brave, which is more cost-effective."

**Note SerpAPI**:
> - `engine` is the key parameter—SerpAPI acts as a proxy for various search engines, so you can switch between Google and Bing simply by changing this line without touching the code. This is the main value add compared to other backends.

> - `gl` and `hl` are useful to expose in the config because they significantly impact result quality depending on the language and country of the query."


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
| **Exa** | API key | AI-oriented, quality snippets |
| **SearpAPI** | API key | 40+ engine, deterministic JSON |
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
# src/mcp_webgate/scraper/fetcher.py

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

- [x] Repo structure and `pyproject.toml`
- [x] `CLAUDE.md` with full context for Claude Code
- [x] Config system (env + toml)
- [x] `scraper/cleaner.py` — lxml pipeline ported from EasySearch
- [x] `scraper/fetcher.py` — httpx concurrent fetcher, UA rotation
- [x] `utils/url.py` — sanitize, dedup, bad_ext filter
- [x] `backends/searxng.py` — first backend
- [x] `tools/fetch.py` — single page MCP tool
- [x] `tools/query.py` — full cycle without LLM query expansion
- [x] `server.py` — tool registration, entry point
- [x] Unit tests for cleaner and fetcher
- [x] Integration test with local SearXNG

### Phase 2 — Multi-backend and quality

- [x] `backends/brave.py`
- [x] `backends/tavily.py`
- [x] Runtime backend selection (tool parameter or config)
- [x] `query` tool accepts `queries: str | list[str]` — model passes multiple queries directly
- [x] Gap Filler (Round 2 fetch)
- [x] Extended test suite

### Phase 3 — Hardening and distribution

- [x] `backends/exa.py`
- [x] `backends/serpapi.py`
- [x] Debug mode with structured logging (`WEBGATE_DEBUG`, `WEBGATE_LOG_FILE`)
- [x] PyPI packaging as `mcp-webgate` (classifiers, URLs, optional `[llm]` extra)
- [x] Docker image (`Dockerfile`)
- [ ] Installation docs for Claude Code / Zed / Cursor
- [x] Config schema validated with Pydantic (`field_validator` on critical fields)

### Phase 4 — External LLM client

Optional, opt-in integrations that delegate intelligence to an external model via a
configurable HTTP client. The server remains fully deterministic when these features
are disabled. All features share a single `[llm]` config block.

**LLM client** — OpenAI-compatible (`base_url` + `api_key` + `model`). Covers:
OpenAI, Ollama, LM Studio, vLLM, Together AI, Groq, and any provider that speaks
the `/v1/chat/completions` protocol. Native Anthropic and Gemini clients considered
as optional adapters.

```toml
[llm]
base_url = "http://localhost:11434/v1"   # Ollama, OpenAI, etc.
api_key  = ""                            # empty for local models
model    = "llama3.2"
timeout  = 15.0
```

**Features to implement:**

- [x] `llm/client.py` — async OpenAI-compatible chat completion client (httpx, no SDK dependency)
- [x] `llm/expander.py` — query expansion: given one query, generate N complementary queries
      (replaces the removed `tools/expander.py`; now via configurable external model)
- [x] `llm/summarizer.py` — results summarization: given sources + original query,
      produce a concise answer in Markdown or JSON with inline citations.
      Input limit is generous (configurable, e.g. 32k chars) — the full cleaned text is passed
      to the summarizer so it can work with rich content. `max_result_length` becomes the target
      length of the summarizer *output* (passed as a prompt guideline, not a hard truncation).
- [x] `utils/reranker.py` — two-tier re-ranking:
      1. **Deterministic** (always active): BM25/TF-IDF keyword overlap between query and
         cleaned text — zero cost, no LLM required, improves over raw backend order by default.
      2. **LLM-assisted** (opt-in, requires `[llm]` configured): given query + title/snippet/
         first ~500 chars per result, returns relevance scores; replaces the deterministic scores.
      Pipeline position: `clean → rerank → top-N → summarizer (if enabled) → output`.
      The LLM reranker uses only lightweight input (no full text) to minimise cost and latency.
- [x] Config: `[llm]` block with `enabled`, `base_url`, `api_key`, `model`, `timeout`
- [x] Config: per-feature flags (`expansion_enabled`, `summarization_enabled`, `llm_rerank_enabled`)
- [x] `query` tool: optional `summarize: bool` parameter — when true, append `summary`
      field to output
- [x] Tests: mock-based unit tests for each LLM feature (no live API calls in CI)
- [x] Docs: `webgate_onboarding` updated to describe LLM features when enabled

### Phase 5 — Rust port

- [ ] Same tool schema (`fetch` and `query`), same API contract
- [ ] `reqwest` + `tokio` for fetching
- [ ] `scraper` crate for HTML cleaning (or `html5ever`)
- [ ] Equivalent backend trait
- [ ] Standalone binary, zero runtime dependencies
- [ ] Publish on crates.io as `mcp-webgate`

---

## 9. Ideas to evaluate / future research

### Structured extractor

Extract specific fields (price, date, author, specs…) from a fetched page as structured JSON.

**Two possible approaches and their trade-offs:**

**A) Deterministic (Python only)** — parse well-known HTML patterns: JSON-LD, OpenGraph `<meta>` tags,
schema.org microdata, common CSS selectors.
- Pro: zero cost, no LLM, fast, works offline
- Con: fragile — breaks when site layout changes; covers only pages that publish structured metadata
- Best as an enrichment layer inside the cleaner (extract JSON-LD/OG tags during the lxml pass already done)
  rather than a separate module. Cost/benefit is reasonable only for this narrow case.

**B) LLM-assisted** — pass cleaned text + field names to an external model, get back JSON.
- Pro: works on any page regardless of markup, handles free-form content
- Con: the invoking model must supply the schema *before* seeing the page — the schema must come
  from the task context (e.g. "user asked for prices → fields: price, name"), not the page structure.
  This works for known-schema tasks but is a dead end for open-ended exploration.
  Furthermore, a flexible summarizer prompt ("extract price and name as JSON") covers the same
  use case without a dedicated module.

**Current verdict:** extractor as a separate feature has weak cost/benefit. JSON-LD/OG enrichment
can be folded into the cleaner cheaply. LLM extraction is covered by a prompt-flexible summarizer.
Revisit if concrete use cases emerge that neither approach handles well.

---

## 10. Features deliberately not ported

| EasySearch feature | Reason for exclusion |
|--------------------|----------------------|
| Auto-translation (`??:en>it`) | Requires LLM in the loop, increases latency |
| Context-aware trigger (`??` empty) | Specific to OWUI chat pipeline |
| Language Anchor | Same as above |
| RAG/retrieval lockdown | Specific to OWUI pipeline |
| Gap Filler | **Included** but disabled by default (latency) |

---

## 11. Claude Code / Zed integration

Configuration in `.mcp.json` or `claude_desktop_config.json`:

```json
{
  "context_servers": { // Use "context_servers" for Zed or "mcpServers" for Claude Code, Windsurf, Cursor:
    "mcp-webgate": {
      "command": "uvx",
      "args": ["mcp-webgate"],
      "env": {
        "WEBGATE_DEFAULT_BACKEND": "searxng",
        "WEBGATE_SEARXNG_URL": "http://localhost:8080",
        "WEBGATE_MAX_RESULT_LENGTH": "4000"
      }
    }
  }
}
```
