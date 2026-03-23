"""Tavily Search API backend."""

from __future__ import annotations

import httpx

from ..config import TavilyConfig
from .base import SearchBackend, SearchResult


class TavilyBackend(SearchBackend):
    """Tavily Search API backend. Requires a free-tier API key."""

    _BASE_URL = "https://api.tavily.com/search"

    def __init__(self, config: TavilyConfig) -> None:
        if not config.api_key:
            raise ValueError("Tavily Search requires WEBGATE_TAVILY_API_KEY to be set")
        self._api_key = config.api_key
        self._search_depth = config.search_depth

    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        payload: dict = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": self._search_depth,
            "max_results": min(num_results, 20),  # Tavily API max is 20
            "include_answer": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._BASE_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("results", []):
            if len(results) >= num_results:
                break
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )
        return results
