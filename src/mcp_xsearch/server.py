"""MCP server entry point: tool registration and stdio transport."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .backends.searxng import SearxngBackend
from .config import load_config
from .tools.fetch import tool_fetch
from .tools.query import tool_query

_config = load_config()
mcp = FastMCP("xsearch", instructions="Denoised web search with context flooding protection.")


def _get_backend(name: str | None = None):
    """Resolve a search backend by name."""
    backend_name = name or _config.backends.default
    if backend_name == "searxng":
        return SearxngBackend(_config.backends.searxng)
    raise ValueError(f"Unknown backend: {backend_name}")


@mcp.tool()
async def fetch(url: str, max_chars: int | None = None) -> str:
    """Fetch and clean a single web page.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters to return (default: server config value).

    Returns denoised text with metadata as JSON.
    """
    result = await tool_fetch(url, _config, max_chars)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def query(
    query: str,
    num_results: int = 5,
    lang: str | None = None,
    backend: str | None = None,
) -> str:
    """Search the web and return denoised, structured results.

    Args:
        query: The search query string.
        num_results: Number of results to return (default: 5).
        lang: Language code for search results (e.g., 'en', 'it').
        backend: Search backend to use (default: config value).

    Returns structured search results with cleaned content as JSON.
    """
    search_backend = _get_backend(backend)
    result = await tool_query(query, search_backend, _config, num_results, lang)
    return json.dumps(result, ensure_ascii=False)


def main():
    """Run the MCP server on stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
