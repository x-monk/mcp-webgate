# mcp-webgate

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-blueviolet)](https://spec.modelcontextprotocol.io/)
[![Latest Release](https://img.shields.io/badge/release-v0.1.24-purple.svg)](https://github.com/annibale-x/mcp-webgate/releases/tag/v0.1.24)

Web search that doesn't wreck your AI's memory.

mcp-webgate is an MCP server that gives your AI clean, bounded web content — across all major AI clients:
- **IDEs**: Claude Desktop, Claude Code, Zed, Cursor, Windsurf, VSCode
- **CLI Agents**: Gemini CLI, Claude CLI, custom agents

## 🌱 A Gentle Introduction

**What is mcp-webgate?**
When your AI uses a standard "fetch URL" tool, it gets the raw HTML of the page — ads, menus, scripts, cookie banners and all. A single news article can dump **200,000 tokens** of garbage into the AI's memory, wiping out your entire conversation.

**mcp-webgate** is a protective filter that sits between your AI and the web:

1. **Strips the junk** — menus, scripts, ads, footers are removed with surgical HTML parsing; only readable text passes through
2. **Hard-caps every response** — no page can ever blow up your context window, no matter how big the original was
3. **Optionally summarizes** — route results through a secondary local LLM that produces a compact Markdown report with citations; your primary AI gets a polished briefing instead of a wall of text

The result: clean, bounded, useful web content — always.

### 🔬 Real example: what happens under the hood

Searching for *"mcp model context protocol"* with LLM features on:

```
Query → LLM expands to 5 search variants → 20 pages found, 13 fetched in parallel

Raw HTML downloaded     5.16 MB   (~1,290,000 tokens)
After cleaning          52.1 KB   (   ~13,000 tokens)  — 99% noise stripped
After LLM summary        5.8 KB   (    ~1,450 tokens)  — structured report with citations
```

**13 sources distilled into ~1,450 tokens.** A single naive fetch of just *one* of those pages (e.g. a security blog at 563 KB) would dump **~140,000 tokens** of raw HTML into your AI's context. webgate processes all 13 and delivers a clean briefing that fits in a footnote.

This is an intensive case (5 queries × 5 results). A typical search with 3–5 results still saves 95%+ of context compared to raw fetching — and your AI gets structured, ranked content instead of a wall of HTML soup.

## 🚀 Quick Start

### 1. Make sure you have `uvx`

```bash
pip install uv
```

`uvx` runs Python tools without installing them permanently. You only need to do this once.

### 2. Set up a search backend

The easiest option is **SearXNG** — free, no account, runs locally:

```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

No Docker? Use a cloud backend instead (Brave, Tavily, Exa, SerpAPI) — see [Backends](#backends).

### 3. Add webgate to your AI client

See the [Integrations](#integrations) table for your specific client. As a quick example, for **Claude Desktop**:

Open the config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this:

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate"],
      "env": {
        "WEBGATE_DEFAULT_BACKEND": "searxng",
        "WEBGATE_SEARXNG_URL": "http://localhost:8080"
      }
    }
  }
}
```

Restart the client after editing.

### 4. Ask your AI to search!

```
Search the web for: latest news on AI regulation
```

The AI will use `webgate_query` automatically. You're done.

## 🔍 How it works

```
Your question
    ↓
Search backend  (SearXNG / Brave / Tavily / Exa / SerpAPI)
    ↓  [deduplicate URLs, block binary files, filter domains]
Fetch pages in parallel  (streaming — hard size cap per page)
    ↓  [optional: retry failed pages from reserve pool]
Strip HTML junk  (menus, ads, scripts, footers — lxml)
    ↓
Clean up text  (invisible chars, unicode junk, BiDi tricks)
    ↓
BM25 reranking  (best-matching results first — always active)
    ↓  [optional: LLM reranking]
Cap total output to budget
    ↓  [optional: LLM summarization → compact Markdown report]
Clean result lands in your AI's context
```

## 🛠️ Tools

webgate gives your AI three tools:

### `webgate_fetch` — read a single page

Use this when you already know the URL you want. The AI passes the URL and gets back the cleaned text — up to `max_query_budget` characters (default 32,000).

```json
{ "url": "https://example.com/article", "max_chars": 32000 }
```

```json
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "text": "cleaned text...",
  "truncated": true,
  "char_count": 12450
}
```

### `webgate_query` — search + fetch + clean

Runs a full search cycle. Pass one query (or several) and get back cleaned, ranked results.

```json
{ "queries": "how to set up a VPN on Linux", "num_results_per_query": 5 }
```

Multiple queries run in parallel and are merged:

```json
{
  "queries": ["VPN Linux setup", "best VPN Linux 2024"],
  "num_results_per_query": 5
}
```

**Output without LLM** — returns cleaned page content for each result:

```json
{
  "sources": [
    { "id": 1, "title": "...", "url": "...", "content": "cleaned text...", "truncated": false }
  ],
  "snippet_pool": [ { "id": 6, "title": "...", "url": "...", "snippet": "..." } ],
  "stats": { "fetched": 5, "total_chars": 18200, "per_page_limit": 6400 }
}
```

**Output with LLM summarization** — returns a compact Markdown report:

```json
{
  "summary": "## How to set up a VPN on Linux\n\nTo install...[1][2]",
  "citations": [{ "id": 1, "title": "...", "url": "..." }],
  "stats": { "fetched": 5, "total_chars": 58000 }
}
```

**Output when LLM fails** — error reason shown, full sources returned as fallback:

```json
{
  "llm_summary_error": "ReadTimeout: LLM did not respond in time",
  "sources": [ "..." ],
  "stats": { "..." : "..." }
}
```

`snippet_pool` contains extra results from the search that were not fetched (search-engine snippet only). The AI can use these to decide if more fetches are worthwhile.

### `webgate_onboarding` — how-to guide

Returns a JSON guide explaining how to use webgate effectively. The AI should call this once at the start of a session if in doubt about which tool to use.

## 🔧 Using webgate with local or smaller models

Most frontier models follow MCP tool instructions automatically. Smaller or local models sometimes ignore the server-provided guidance and fall back to a built-in fetch tool instead — returning raw HTML that floods the context with noise.

If you notice this happening, add an explicit instruction block to your system prompt:

```
You have access to webgate tools for web search and page retrieval.
Follow these rules in every session:
- To search the web: use webgate_query — never use a built-in fetch, browser, or HTTP tool
- To retrieve a URL: use webgate_fetch — never fetch URLs directly
- Built-in fetch tools return raw HTML that floods your context; webgate returns clean, bounded text
At the start of each session, call webgate_onboarding to read the full operational guide.
```

This works because user system prompt instructions take precedence over MCP server-level guidance, making the constraint explicit at the highest-priority layer the model sees.

> **Tip:** if your client supports named system prompts or prompt templates, save the block above as a reusable preset so you don't have to paste it every time.

## 🎛️ Tuning

This section explains what the key parameters do and when to change them. The defaults work well for most cases — only tweak if you have a specific reason.

### What is a "character budget"?

webgate measures text in **characters** (not tokens). A rough conversion for English text:

> 4 characters ≈ 1 token

| Characters | Approximate tokens |
|------------|-------------------|
| 8,000 | ~2,000 |
| 32,000 | ~8,000 |
| 96,000 | ~24,000 |

### `webgate_fetch` budget

When you fetch a single URL, the ceiling is `max_query_budget` (default **32,000 chars**). The tool parameter `max_chars` can request less, but never more than this ceiling.

**Why `max_query_budget` and not `max_result_length`?** Because you're fetching one page — the "total output" IS that one page, so the right limit is the overall context budget, not the per-page cap designed for multi-source queries.

### `webgate_query` budget — without LLM

With no LLM, the cleaned sources go directly to your AI's context. webgate distributes `max_query_budget` across all fetched pages so the total never exceeds the budget:

> **Per-page limit** = `max_query_budget` ÷ number of results
> (capped at `max_result_length`)

| Results fetched | Per-page limit | Total output |
|-----------------|---------------|-------------|
| 1 | 8,000 (cap) | ≤ 8,000 |
| 5 | 6,400 | ≤ 32,000 |
| 10 | 3,200 | ≤ 32,000 |
| 20 | 1,600 | ≤ 32,000 |

The total output is always at most `max_query_budget`, regardless of how many results you request — the per-page share automatically shrinks to compensate.

### `webgate_query` budget — with LLM summarization

When a secondary LLM is summarizing, it *compresses* the content before passing the result to your primary AI. This means it's safe — and beneficial — to give it more raw material to work from.

webgate scales up the input using `input_budget_factor` (default **3**):

> **LLM input budget** = `max_query_budget` × `input_budget_factor`
> Default: 32,000 × 3 = **96,000 chars**

| Results fetched | LLM input / page | Total LLM input | Output to your AI |
|-----------------|-----------------|----------------|------------------|
| 1 | 96,000 | 96,000 | compact report |
| 5 | 19,200 | 96,000 | compact report |
| 10 | 9,600 | 96,000 | compact report |
| 20 | 4,800 | 96,000 | compact report |

The secondary LLM sees much more content per page. Your primary AI sees only the final report — typically **1,000–3,000 tokens** — regardless of how many sources were processed. This is the main efficiency advantage of LLM mode.

### Quick tuning guide

| Symptom | Fix |
|---------|-----|
| AI responses feel slow, too much text | Reduce `max_query_budget` (e.g. `16000`) |
| AI answers are shallow or miss details | Increase `max_query_budget` (e.g. `48000`) |
| LLM summary is thin or misses things | Increase `input_budget_factor` (e.g. `5`) |
| LLM summary times out or is very slow | Reduce `input_budget_factor` (e.g. `2`) or reduce `results_per_query` |
| `fetch` returns too little of a long page | Increase `max_query_budget` (e.g. `64000`) |
| Pages are slow to download | Reduce `max_download_mb` (e.g. `1`, already default) |
| Server downloads too much garbage | Reduce `max_download_mb` (e.g. `1`) |

## 🤖 LLM Features

Optional, opt-in. When `llm.enabled = false` (the default), webgate is fully deterministic. Enable the `[llm]` block to unlock three extra capabilities.

### 🤔 When to enable LLM features

| Situation | Recommended setup | Typical latency overhead |
|-----------|------------------|--------------------------|
| Fast answers, general research | LLM **disabled** (default) — BM25-ranked clean sources, zero latency overhead | none |
| Deep research on a complex topic | **Summarization on** — get a cited Markdown report instead of raw pages | +5–30s |
| Broad topic, one query isn't enough | **Expansion + Summarization** — LLM generates variants and synthesizes all results | +6–35s |
| Result order matters more than speed | **LLM reranking on** — semantic ordering at the cost of one extra LLM call per query | +1–5s |

**Privacy:** with LLM disabled, no data leaves your machine except web requests. With LLM enabled, cleaned search results (not raw HTML) are sent to the configured `base_url`. Point it at a local Ollama instance to keep everything on-device.

**Latency trade-off:** each enabled feature adds one LLM round-trip per query. Expansion adds ~1–5s; summarization adds ~5–30s depending on model and content volume. For interactive use, summarization with a fast local model (e.g. Gemma 3 4B) is a good starting point.

### Setup

```toml
[llm]
enabled  = true
base_url = "http://localhost:11434/v1"   # Ollama, OpenAI, LM Studio, vLLM, Groq...
api_key  = ""                            # empty for local models
model    = "gemma3:27b"
timeout  = 60                            # local 27B+ models may need up to 60s
```

Or with env vars:

```json
"env": {
  "WEBGATE_LLM_ENABLED": "true",
  "WEBGATE_LLM_BASE_URL": "http://localhost:11434/v1",
  "WEBGATE_LLM_MODEL": "gemma3:27b",
  "WEBGATE_LLM_TIMEOUT": "60"
}
```

`base_url` accepts any OpenAI-compatible endpoint: **OpenAI**, **Ollama**, **LM Studio**, **vLLM**, **Together AI**, **Groq**, and others.

### Query expansion

When you send a single query and `expansion_enabled = true`, the LLM automatically generates complementary search variants before hitting the backend. If you already pass multiple queries, this step is skipped.

```
"best laptop for programming"
    ↓ expansion
["best laptop for programming 2024", "developer laptop recommendations", "laptop specs for coding"]
    ↓ all search in parallel
```

Falls back silently to your original query if the LLM fails.

### Summarization

When `summarization_enabled = true`, the LLM reads all fetched pages and writes a structured Markdown report with inline citations. Your AI receives the report instead of the raw text.

- **Success**: `summary` + `citations` (lean output — no raw content passed to your AI)
- **Failure**: `llm_summary_error` with the reason + full `sources` as fallback (your AI can still work with the cleaned content)

The report length target is `max_summary_words`. When `0` (default), it is derived from `max_query_budget / 5` — e.g. with a 32k budget, the target is ~6,400 words.

### Reranking

Results are always reranked by BM25 (keyword overlap, zero cost) before being returned. Optionally, the LLM can do a second pass for semantic relevance:

| Tier | When | Cost |
|------|------|------|
| **BM25** (deterministic) | Always | Zero — pure math |
| **LLM-assisted** | `llm_rerank_enabled = true` | One LLM call per query |

LLM reranking adds latency proportional to your LLM response time. Enable it only if result ordering matters more than speed.

Pipeline: `clean → BM25 rerank → (LLM rerank) → (LLM summarize) → output`

## 🔗 Integrations

mcp-webgate works with all major AI clients:

| Platform | Configuration Guide | Notes |
|----------|---------------------|-------|
| **Claude Desktop** | [IDE Integration](docs/integrations/IDE.md#claude-desktop) | Desktop application |
| **Claude Code** | [IDE Integration](docs/integrations/IDE.md#claude-code) | CLI coding agent |
| **Zed Editor** | [IDE Integration](docs/integrations/IDE.md#zed-editor) | Native MCP support |
| **Cursor** | [IDE Integration](docs/integrations/IDE.md#cursor) | Requires Agent mode |
| **Windsurf** | [IDE Integration](docs/integrations/IDE.md#windsurf) | Global config only |
| **VSCode** | [IDE Integration](docs/integrations/IDE.md#vscode) | Via Copilot or MCP extension |
| **Gemini CLI** | [Agent Integration](docs/integrations/AGENT.md#gemini-cli) | Google's CLI agent |
| **Claude CLI** | [Agent Integration](docs/integrations/AGENT.md#claude-cli) | Anthropic's CLI agent |

## 📦 Installation

### Via uvx (recommended — no install needed)

```bash
uvx mcp-webgate
```

### Via pip / uv

```bash
pip install mcp-webgate
# or
uv add mcp-webgate
```

## ⚙️ Full Configuration

Ready-to-use config files are in [`examples/`](examples/).

### Resolution order

```
CLI args  >  env vars  >  webgate.toml  >  defaults
```

Config is read once at startup; restart the server to apply changes.

You can configure webgate in three ways — mix and match as needed:

- **`webgate.toml`** — checked at startup in `./webgate.toml` then `~/webgate.toml`
- **Env vars** — `WEBGATE_*` prefix, always strings (MCP JSON requirement)
- **CLI args** — `--kebab-case`, integers stay integers, ideal for multi-instance setups

### Config file (`webgate.toml`)

```toml
[server]
max_download_mb    = 1        # how many MB to download per page before cutting off
max_result_length  = 8000     # max chars per page in multi-source queries (no LLM)
max_query_budget   = 32000    # total char budget for a fetch, or input pool for a query
max_search_queries = 5        # max parallel queries per call
results_per_query  = 5        # results to fetch per query
search_timeout     = 8        # seconds before giving up on a page
oversampling_factor = 2       # fetch 2× more candidates than needed (dedup reserve)
auto_recovery_fetch = false   # retry failed fetches from reserve pool
max_total_results  = 20       # hard cap: never fetch more than this many pages total
blocked_domains    = ["reddit.com", "pinterest.com"]
allowed_domains    = []       # if non-empty, only these domains are allowed
adaptive_budget    = false   # [EXPERIMENTAL] proportional char allocation based on BM25 rank
adaptive_budget_fetch_factor = 3  # generous pre-rank fetch multiplier

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
model    = "llama3.2"
timeout  = 60
expansion_enabled     = true
summarization_enabled = true
llm_rerank_enabled    = false
max_summary_words     = 0     # 0 = max_query_budget / 5 (e.g. 6400 with budget 32000)
input_budget_factor   = 3     # LLM input = max_query_budget × factor (default: 96000)
```

### MCP client config examples

**With env vars** (all values must be strings):

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate"],
      "env": {
        "WEBGATE_DEFAULT_BACKEND": "searxng",
        "WEBGATE_SEARXNG_URL": "http://localhost:8080",
        "WEBGATE_LLM_ENABLED": "true",
        "WEBGATE_LLM_TIMEOUT": "60"
      }
    }
  }
}
```

**With CLI args** (integers stay integers — ideal for running independent instances in Zed, Cursor, etc.):

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": [
        "mcp-webgate",
        "--searxng-url", "http://localhost:8080",
        "--llm-enabled",
        "--llm-model", "gemma3:27b",
        "--llm-timeout", "60"
      ]
    }
  }
}
```

Boolean flags support `--flag` / `--no-flag` syntax (e.g. `--llm-enabled`, `--no-llm-rerank-enabled`).

### Full reference

| CLI argument | Env var | Default | Description |
|---|---|---|---|
| `--default-backend` | `WEBGATE_DEFAULT_BACKEND` | `searxng` | Active backend |
| `--searxng-url` | `WEBGATE_SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |
| `--brave-api-key` | `WEBGATE_BRAVE_API_KEY` | _(empty)_ | Brave Search API key |
| `--tavily-api-key` | `WEBGATE_TAVILY_API_KEY` | _(empty)_ | Tavily API key |
| `--exa-api-key` | `WEBGATE_EXA_API_KEY` | _(empty)_ | Exa API key |
| `--serpapi-api-key` | `WEBGATE_SERPAPI_API_KEY` | _(empty)_ | SerpAPI key |
| `--serpapi-engine` | `WEBGATE_SERPAPI_ENGINE` | `google` | SerpAPI engine (`google`, `bing`, ...) |
| `--serpapi-gl` | `WEBGATE_SERPAPI_GL` | `us` | SerpAPI country code |
| `--serpapi-hl` | `WEBGATE_SERPAPI_HL` | `en` | SerpAPI language |
| `--max-download-mb` | `WEBGATE_MAX_DOWNLOAD_MB` | `1` | Per-page download size cap (MB) |
| `--max-result-length` | `WEBGATE_MAX_RESULT_LENGTH` | `8000` | Per-page char cap (no-LLM queries) |
| `--max-query-budget` | `WEBGATE_MAX_QUERY_BUDGET` | `32000` | Total char budget for fetch and query |
| `--max-search-queries` | `WEBGATE_MAX_SEARCH_QUERIES` | `5` | Max queries per call |
| `--results-per-query` | `WEBGATE_RESULTS_PER_QUERY` | `5` | Default results fetched per query |
| `--search-timeout` | `WEBGATE_SEARCH_TIMEOUT` | `8` | HTTP request timeout (seconds) |
| `--oversampling-factor` | `WEBGATE_OVERSAMPLING_FACTOR` | `2` | Search result multiplier for dedup reserve |
| `--auto-recovery-fetch` | `WEBGATE_AUTO_RECOVERY_FETCH` | `false` | Enable gap-filler (Round 2 fetch) |
| `--max-total-results` | `WEBGATE_MAX_TOTAL_RESULTS` | `20` | Hard cap on total results per call |
| `--debug` | `WEBGATE_DEBUG` | `false` | Enable structured debug logging |
| `--log-file` | `WEBGATE_LOG_FILE` | _(empty)_ | Log file path (empty = stderr) |
| `--trace` | `WEBGATE_TRACE` | `false` | Include content in summarized citations; also activates debug logging |
| `--adaptive-budget` | `WEBGATE_ADAPTIVE_BUDGET` | `false` | [EXPERIMENTAL] Proportional char allocation based on BM25 rank |
| `--adaptive-budget-fetch-factor` | `WEBGATE_ADAPTIVE_BUDGET_FETCH_FACTOR` | `3` | [EXPERIMENTAL] Generous pre-rank fetch multiplier |
| `--llm-enabled` | `WEBGATE_LLM_ENABLED` | `false` | Enable LLM features |
| `--llm-base-url` | `WEBGATE_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `--llm-api-key` | `WEBGATE_LLM_API_KEY` | _(empty)_ | API key (empty for local models) |
| `--llm-model` | `WEBGATE_LLM_MODEL` | `llama3.2` | Model name |
| `--llm-timeout` | `WEBGATE_LLM_TIMEOUT` | `30` | LLM request timeout (seconds) |
| `--llm-expansion-enabled` | `WEBGATE_LLM_EXPANSION_ENABLED` | `true` | Auto-expand queries into variants |
| `--llm-summarization-enabled` | `WEBGATE_LLM_SUMMARIZATION_ENABLED` | `true` | LLM summary with citations |
| `--llm-rerank-enabled` | `WEBGATE_LLM_RERANK_ENABLED` | `false` | LLM-assisted reranking |
| `--llm-max-summary-words` | `WEBGATE_LLM_MAX_SUMMARY_WORDS` | `0` | Summary word target (0 = auto) |
| `--llm-input-budget-factor` | `WEBGATE_LLM_INPUT_BUDGET_FACTOR` | `3` | LLM input budget multiplier |

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

Then set `WEBGATE_SEARXNG_URL=http://localhost:8080`.

### Exa notes

Exa uses neural (semantic) search by default — the primary reason to use it over keyword backends. `use_autoprompt` is hardcoded to `false` (not user-configurable) because mcp-webgate handles query expansion via its own LLM expander.

### SerpAPI notes

`engine` selects the underlying search engine (`google`, `bing`, `duckduckgo`, `yandex`, `yahoo`). `gl` and `hl` significantly affect result quality for non-English queries.

## 🐛 Debug mode

When enabled, every tool call logs a structured entry:

- **`fetch`**: URL, raw KB downloaded, clean KB returned, elapsed ms
- **`query`**: queries used, results requested/fetched/failed, raw MB, clean KB, total elapsed ms

```bash
export WEBGATE_DEBUG=true             # log to stderr
export WEBGATE_LOG_FILE=/tmp/wg.log  # or log to file
```

## 🛡️ Protections summary

These protections are always active — they are the core value proposition and cannot be disabled.

| What could go wrong | How webgate stops it |
|---------------------|---------------------|
| Page dumps 2 MB of HTML | `max_download_mb` hard cap — download stops mid-stream, never buffered |
| Cleaned text is still huge | `max_result_length` char cap per page |
| Many results flood the context | `max_query_budget` distributes a fixed total across all results |
| Too many pages fetched | `max_total_results` hard cap |
| PDF / ZIP / DOCX requested | Binary extension filter runs *before* any network request |
| Slow or hanging connections | `search_timeout` + 5s connect timeout |
| Invisible Unicode tricks in content | Full regex sterilization pipeline (zero-width, BiDi, etc.) |
| Rate limiting (429 / 502 / 503) | Exponential retry backoff, respects `Retry-After` header |
| Unwanted domains | `blocked_domains` / `allowed_domains` filter |

## 📚 Documentation Structure

### Integration Guides
- **[IDE Integration](docs/integrations/IDE.md)** — Claude Desktop, Claude Code, Zed, Cursor, Windsurf, VSCode
- **[Agent Integration](docs/integrations/AGENT.md)** — Gemini CLI, Claude CLI, custom agents
- **[Advanced Features](ADVANCED.md)** — BM25/LLM reranking internals, adaptive budget allocation

<!-- RECENT_CHANGES_START -->
<!-- RECENT_CHANGES_END -->

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on:
- Development setup and workflow
- Code style and conventions
- Testing requirements
- Documentation standards
- Pull request process

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🔗 Links

- **[GitHub Repository](https://github.com/annibale-x/mcp-webgate)** — Source code and issues
- **[PyPI Package](https://pypi.org/project/mcp-webgate/)** — Python Package Index
- **[MCP Registry](https://registry.modelcontextprotocol.io/?q=mcp-webgate&all=1)** — Model Context Protocol Registry
- **[MCP Protocol](https://modelcontextprotocol.io/specification/2025-11-25)** — Model Context Protocol specification

---

**Need help?** Check the [documentation](docs/) or open an [issue](https://github.com/annibale-x/mcp-webgate/issues) on GitHub.

<!-- mcp-name: io.github.annibale-x/mcp-webgate -->
