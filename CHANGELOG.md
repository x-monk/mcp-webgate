# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-21

### Added
- MCP server with `fetch` and `query` tools
- Config system: env vars > `xsearch.toml` > defaults (Pydantic + tomllib)
- HTML cleaning pipeline: lxml XPath removal + regex text sterilization (unicode, BiDi, noise lines)
- Async HTTP fetcher: httpx streaming with UA rotation (20 agents) and per-page size cap
- SearXNG search backend
- URL utilities: tracking param removal, dedup, binary extension filter
- Oversampling + optional gap filler (Round 2 fetch) in `query` tool
- Snippet injection for unread pages (reserve pool)
- Anti-context-flooding protections: `max_download_mb`, `max_result_length`, `max_total_results`
- 33 unit tests (cleaner, config, URL utils)

[Unreleased]: https://github.com/annibale-x/mcp-xsearch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/annibale-x/mcp-xsearch/releases/tag/v0.1.0
