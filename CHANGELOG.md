# Changelog

* 2026-03-22: v0.1.6 - robot.py hardening, Phase 4 pipeline design (Hannibal)
  * chore(robot): update README release badge on bump
  * chore(robot): auto-push dev to origin after bump commit
  * docs(plan): Phase 4 LLM pipeline redesign — reranker two-tier (deterministic BM25 always active, LLM opt-in), summarizer receives generous input (max_result_length becomes output target), extractor moved to "Ideas to evaluate" section with cost/benefit analysis

* 2026-03-22: v0.1.5 - Multi-query tool interface, onboarding tool (Hannibal)
  * feat(query): queries parameter accepts str | list[str] — model passes queries directly, no server-side LLM
  * feat(query): max_queries config cap (default 5) — silently truncates overlength lists
  * feat(query): output field renamed query_used -> queries
  * feat(server): xsearch_onboarding tool — returns JSON guide for models (tools, protections, tips)
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
  * feat(config): Pydantic config system with env vars, xsearch.toml, and defaults
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
