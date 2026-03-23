"""MCP server entry point: tool registration and stdio transport."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .backends.brave import BraveBackend
from .backends.exa import ExaBackend
from .backends.searxng import SearxngBackend
from .backends.serpapi import SerpapiBackend
from .backends.tavily import TavilyBackend
from .config import load_config, parse_cli_args
from .tools.fetch import tool_fetch
from .tools.query import tool_query
from .utils.logger import setup_debug_logging

_config = load_config()

mcp = FastMCP("webgate", instructions="Denoised web search with context flooding protection.")


def _get_backend(name: str | None = None):
    """Resolve a search backend by name."""
    backend_name = name or _config.backends.default
    if backend_name == "searxng":
        return SearxngBackend(_config.backends.searxng)
    if backend_name == "brave":
        return BraveBackend(_config.backends.brave)
    if backend_name == "tavily":
        return TavilyBackend(_config.backends.tavily)
    if backend_name == "exa":
        return ExaBackend(_config.backends.exa)
    if backend_name == "serpapi":
        return SerpapiBackend(_config.backends.serpapi)
    raise ValueError(
        f"Unknown backend: {backend_name!r}. "
        "Valid options: searxng, brave, tavily, exa, serpapi"
    )


@mcp.tool()
async def webgate_onboarding() -> str:
    """Return operational guide for using webgate tools effectively.

    Call this once before your first search session to understand how to get
    the best results from the available tools.
    """
    guide = {
        "tools": {
            "fetch": {
                "purpose": "Retrieve and clean a single URL you already know.",
                "when_to_use": "When you have a specific URL and want its content.",
                "key_params": {
                    "url": "The URL to fetch.",
                    "max_chars": "Character cap for returned text (default: server config).",
                },
            },
            "query": {
                "purpose": "Search the web, fetch top results in parallel, return denoised structured content.",
                "when_to_use": "When you need to research a topic across multiple sources.",
                "key_params": {
                    "queries": (
                        "One query string OR a list of query strings (up to max_search_queries). "
                        f"Server cap: {_config.server.max_search_queries}. "
                        "Tip: pass complementary/specialized queries for broader coverage — "
                        "e.g. ['python asyncio tutorial', 'asyncio best practices 2024', 'asyncio pitfalls']."
                    ),
                    "num_results_per_query": (
                        f"Results to fetch per query (default: {_config.server.results_per_query}). "
                        "Total = num_results_per_query × number_of_queries, "
                        f"bounded by max_total_results ({_config.server.max_total_results}). "
                        f"Example: 3 queries × {_config.server.results_per_query} = {3 * _config.server.results_per_query} total results."
                    ),
                    "lang": "Language code, e.g. 'en', 'it', 'de' (optional).",
                    "backend": "Search engine: searxng | brave | tavily | exa | serpapi (default: server config).",
                },
                "output": {
                    "queries": "The query/queries actually used.",
                    "sources": "Fetched and cleaned pages. Each has: id, title, url, snippet, content, truncated.",
                    "snippet_pool": "Extra results from oversampling reserve (snippet only, no fetch). Use url+snippet to decide if worth fetching.",
                    "stats": "fetched, failed, gap_filled, total_chars, per_page_limit, num_results_per_query.",
                },
            },
        },
        "protections": {
            "max_download_mb": f"{_config.server.max_download_mb} MB — hard cap on raw page download.",
            "max_result_length": f"{_config.server.max_result_length} chars — per-page ceiling.",
            "max_query_budget": f"{_config.server.max_query_budget} chars — total budget distributed across all sources in a query call.",
            "max_search_queries": f"{_config.server.max_search_queries} — maximum number of queries per call (including LLM-expanded variants).",
            "binary_filter": "PDF, ZIP, DOCX and other binary files are blocked before any network request.",
            "dedup": "URLs are deduplicated and tracking parameters stripped before fetching.",
        },
        "tips": [
            "Use multiple complementary queries to improve result diversity.",
            "Check snippet_pool before making additional fetch calls — the snippet may already answer your question.",
            "If a source is truncated=true, consider calling fetch directly on that URL with a higher max_chars.",
            "Use lang= to get results in a specific language.",
        ],
    }

    if _config.llm.enabled:
        guide["llm_features"] = {
            "status": "enabled",
            "model": _config.llm.model,
            "expansion": (
                "active — single queries are automatically expanded into complementary variants"
                if _config.llm.expansion_enabled else "disabled"
            ),
            "summarization": (
                "active — every query response includes a Markdown summary with inline citations"
                if _config.llm.summarization_enabled else "disabled"
            ),
            "reranking": (
                "llm-assisted active (deterministic BM25 also active)"
                if _config.llm.llm_rerank_enabled else "deterministic BM25 only"
            ),
        }
    else:
        guide["llm_features"] = {
            "status": "disabled",
            "note": "Set WEBGATE_LLM_ENABLED=true and configure WEBGATE_LLM_BASE_URL/MODEL to enable query expansion, summarization, and LLM reranking.",
        }

    return json.dumps(guide, ensure_ascii=False, indent=2)


@mcp.tool()
async def webgate_fetch(url: str, max_chars: int | None = None) -> str:
    """Fetch and clean a single web page.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters to return (default: server config value).

    Returns denoised text with metadata as JSON.
    """
    result = await tool_fetch(url, _config, max_chars)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def webgate_query(
    queries: str | list[str],
    num_results_per_query: int = 5,
    lang: str | None = None,
    backend: str | None = None,
) -> str:
    """Search the web and return denoised, structured results.

    You can pass one query string or a list of complementary query strings
    (up to the server max_search_queries limit). Multiple queries run in parallel
    and results are merged in round-robin order to avoid single-query dominance.

    num_results_per_query controls results fetched *per query*. With 3 queries
    and num_results_per_query=5 the pipeline targets 15 total results (bounded
    by the server max_total_results hard cap).

    Examples:
      Single:   queries="python asyncio tutorial"
      Multi:    queries=["python asyncio tutorial", "asyncio pitfalls", "asyncio vs threading"]

    Args:
        queries: One search query string, or a list of query strings.
        num_results_per_query: Results to fetch and clean per query (default: 5).
        lang: Language code for search results (e.g., 'en', 'it').
        backend: Search backend to use (default: config value).
                 Valid options: searxng, brave, tavily, exa, serpapi.

    Returns structured search results with cleaned content as JSON.
    If LLM summarization is enabled in server config, results include a `summary` field.
    """
    search_backend = _get_backend(backend)
    result = await tool_query(queries, search_backend, _config, num_results_per_query, lang, trace=_config.server.trace)
    return json.dumps(result, ensure_ascii=False)


def main():
    """Run the MCP server on stdio."""
    global _config
    _config = load_config(parse_cli_args())
    if _config.server.debug or _config.server.trace:
        setup_debug_logging(_config.server.log_file)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
