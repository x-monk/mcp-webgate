# Changelog

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
