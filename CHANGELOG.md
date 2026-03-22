# Changelog

* 2026-03-22: v0.1.13 - Per-query debug grouping and aligned log output (Hannibal)
  * feat(logger): group fetch rows by originating query when expansion/multi-query active
  * feat(logger): fix [fail] row alignment — ms column now matches [ok] rows via fixed-width data_str
  * feat(logger): summary line now shows raw/clean/output (output=summary KB if LLM, else =clean)
  * feat(logger): expand= timing only shown when expansion actually ran (>= 100ms threshold)
  * feat(query): track url_to_query_idx during round-robin flatten; pass query_idx in fetch_details

* 2026-03-22: v0.1.12 - Detailed debug logging and Zed config (Hannibal)
  * feat(logger): multi-line query log with timing breakdown (expand/search/fetch/total), per-URL fetch rows (raw KB → clean KB, elapsed ms), and totals summary
  * feat(fetcher): _fetch_single now returns (html, elapsed_ms, raw_bytes) tuple; fetch_urls returns (html_map, timing_map)
  * feat(query): timing checkpoints for expansion, search, fetch phases; fetch_details collected during assembly
  * feat(robot): add `install` command — uninstall, clean cache, rebuild, install as uv tool
  * docs(readme): add Zed `context_servers` configuration section (minimal + LLM/debug variant)
  * docs(contributing): document `install` command in daily commands
  * test(fetcher): updated for new tuple return type
  * test(query): updated mock return values for new fetch_urls signature
  * test(logger): updated assertions for new log format

* 2026-03-22: v0.1.11 - num_results_per_query semantic (Hannibal)
  * feat(query): rename num_results → num_results_per_query; total = per_query × num_queries bounded by max_total_results (e.g. 3 queries × 5 = 15 results)
  * feat(query): num_results_per_query added to stats output
  * feat(server): query tool parameter and docstring updated; onboarding updated with new param and summarize param
  * test(query): all num_results= calls updated to num_results_per_query=
  * docs(readme): query input/output examples updated; multi-query section clarified

* 2026-03-22: v0.1.10 - Documentation overhaul (Hannibal)
  * docs(readme): Gentle Introduction — context flooding problem, pipeline diagram, summarization advantage with self-hosted models
  * docs(readme): full Phase 4 LLM features section (expansion, summarization, reranking); TOC; emoji topic headers
  * docs(contributing): updated project structure (llm/ module, utils/reranker.py, correct test files); LLM config and env vars; anti-flooding table updated with retry backoff row; release workflow reflects bump→push and README badge update; testing patterns for async context managers and MagicMock vs AsyncMock; TOC; emoji headers

* 2026-03-22: v0.1.9 - Test suite warning cleanup (Hannibal)
  * fix(test_llm): proper async context manager mocking — __aenter__/__aexit__ set explicitly, no more internal coroutine leak
  * fix(test_fetcher): response objects changed from AsyncMock to MagicMock; only actually-awaited methods (aclose, send) stay AsyncMock
  * chore(pytest): filterwarnings for known CPython 3.11 AsyncMock _execute_mock_call issue (github.com/python/cpython/issues/91610)
  * fix(test_integration_searxng): query_used renamed to queries since v0.1.4

* 2026-03-22: v0.1.8 - Live LLM integration tests (Hannibal)
  * test(integration): test_integration_llm.py — 10 live tests against Ollama (gemma3:27b): LLMClient chat, expander variants, summarizer citations, LLM reranker relevance; auto-skip if Ollama unreachable

* 2026-03-22: v0.1.7 - Phase 4 — External LLM client (Hannibal)
  * feat(llm): LLMClient — async OpenAI-compatible /v1/chat/completions client (httpx, no SDK)
  * feat(llm): expander.py — single-query auto-expansion to N complementary queries via LLM
  * feat(llm): summarizer.py — Markdown summary with inline citations; receives full cleaned text (generous input_limit), max_result_length becomes output target guideline
  * feat(utils): reranker.py — two-tier: deterministic BM25 (always active) + LLM-assisted opt-in (title+snippet+200 chars input only)
  * feat(config): LLMConfig block — enabled, base_url, api_key, model, timeout, expansion_enabled, summarization_enabled, llm_rerank_enabled, summarizer_input_limit
  * feat(config): WEBGATE_LLM_* env var mappings
  * feat(query): summarize: bool parameter — appends summary field when LLM is configured
  * refactor(query): pipeline order: search → fetch → clean → BM25 rerank → (LLM rerank) → (summarize) → output
  * feat(server): webgate_onboarding reports LLM feature status (enabled/disabled per feature)
  * test(llm): test_llm.py — 21 mock-based cases: LLMClient, expander, summarizer, reranker (det. + LLM)

* 2026-03-22: v0.1.6 - robot.py hardening, Phase 4 pipeline design (Hannibal)
  * chore(robot): update README release badge on bump
  * chore(robot): auto-push dev to origin after bump commit
  * docs(plan): Phase 4 LLM pipeline redesign — reranker two-tier (deterministic BM25 always active, LLM opt-in), summarizer receives generous input (max_result_length becomes output target), extractor moved to "Ideas to evaluate" section with cost/benefit analysis

* 2026-03-22: v0.1.5 - Multi-query tool interface, onboarding tool (Hannibal)
  * feat(query): queries parameter accepts str | list[str] — model passes queries directly, no server-side LLM
  * feat(query): max_queries config cap (default 5) — silently truncates overlength lists
  * feat(query): output field renamed query_used -> queries
  * feat(server): webgate_onboarding tool — returns JSON guide for models (tools, protections, tips)
  * refactor(server): removed expander.py and all Anthropic API calls — server is now fully deterministic
  * refactor(config): removed query_expansion, expansion_model, expansion_max_queries; added max_queries
  * test(query): test_query.py — single/multi query, cap enforcement, round-robin, budget (9 cases)

* 2026-03-22: v0.1.4 - Multi-query parallel merging (Hannibal)
  * fix(query): all expanded queries now run in parallel via asyncio.gather (was: only queries[0] used)
  * feat(query): results from multiple queries merged in round-robin order to avoid single-query dominance
  * feat(query): query_used is a list when expansion returns multiple queries, string when single
  * test(query): parallel search call count, round-robin interleaving, query_used as list

* 2026-03-22: v0.1.3 - Retry backoff, domain filter (Hannibal)
  * feat(fetcher): exponential retry backoff on 429/502/503 with Retry-After header support
  * feat(url): is_domain_allowed() — blocklist and allowlist with subdomain matching
  * feat(fetch): domain filter applied before network request
  * feat(query): domain filter applied during URL dedup pass
  * feat(config): blocked_domains and allowed_domains lists (toml only)
  * test(fetcher): TestRetryBackoff — 5 cases (429 retry, 503, exhausted, Retry-After, 404 no-retry)
  * test(url): TestIsDomainAllowed — 8 cases (blocklist, subdomain, allowlist precedence)

* 2026-03-22: v0.1.2 - Typography normalization, sliding window, query budget (Hannibal)
  * feat(cleaner): normalize_typography() — smart quotes, em/en dash, ellipsis, ligatures, soft hyphen
  * feat(cleaner): sliding window truncation on line boundaries instead of hard char cut
  * feat(query): max_query_budget — distributes total char budget evenly across results
  * feat(query): per_page_limit exposed in stats output
  * fix(cleaner): extract_title now applies typography normalization to titles
  * fix(robot): unicode arrow replaced with ASCII to fix cp1252 encoding on Windows
  * test(cleaner): TestNormalizeTypography (7 cases) and TestApplyWindow (5 cases)
  * test(query): TestQueryBudget — per_page distribution, ceiling cap, total bounded by budget

* 2026-03-22: v0.1.1 - Multi-backend, debug mode, Phase 2+3 (Hannibal)
  * feat(backends): Brave Search API backend with safesearch and lang support
  * feat(backends): Tavily Search API backend with configurable search_depth
  * feat(backends): Exa neural search backend (useAutoprompt always disabled)
  * feat(backends): SerpAPI proxy backend (Google, Bing, DuckDuckGo, Yandex, Yahoo)
  * feat(query): optional LLM query expansion via Anthropic SDK (fallback-safe)
  * feat(query): gap filler (Round 2 fetch) promoted to tested feature
  * feat(server): runtime backend selection via tool parameter
  * feat(debug): structured debug logging with log_fetch and log_query helpers
  * feat(config): Pydantic field_validator on critical numeric fields
  * feat(config): ExaConfig and SerpapiConfig with all documented parameters
  * chore(pkg): PyPI classifiers, keywords, project URLs, optional [llm] extra
  * chore(docker): Dockerfile with uv, python:3.11-slim, non-root user
  * fix(robot): replace unicode arrow with ASCII to fix cp1252 encoding on Windows
  * test(backends): mock-based unit tests for Brave, Tavily, Exa, SerpAPI
  * test(expander): LLM expansion mocking, fallback paths, markdown fence stripping
  * test(debug): logger setup, log_fetch, log_query output, config validators
  * test(integration): live SearXNG integration tests (auto-skip if unavailable)


* 2026-03-21: v0.1.0 - Initial MVP (Hannibal)
  * feat(server): MCP entry point with `fetch` and `query` tools via FastMCP
  * feat(config): Pydantic config system with env vars, webgate.toml, and defaults
  * feat(cleaner): lxml XPath pipeline + regex sterilization (unicode, BiDi, noise lines)
  * feat(fetcher): httpx async streaming fetcher with UA rotation and per-page size cap
  * feat(backends): SearXNG backend with abstract SearchBackend interface
  * feat(url): URL sanitization, dedup, and binary extension filter
  * feat(query): oversampling, optional gap filler, and snippet injection for reserve pool
  * test(cleaner): full pipeline coverage (lxml, text cleaning, title extraction, truncation)
  * test(config): defaults, max_download_bytes, env var overrides
  * test(url): sanitize, binary filter, dedup with tracking-param normalization
  * docs(scripts): robot.py automation — test/build/bump/promote/publish
  * docs(contributing): developer guide with setup, config, release workflow
