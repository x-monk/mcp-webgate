"""Brave Search API backend."""

from __future__ import annotations

import httpx

from ..config import BraveConfig
from .base import SearchBackend, SearchResult


class BraveBackend(SearchBackend):
    """Brave Search API backend. Requires a free-tier API key."""

    _BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, config: BraveConfig) -> None:
        if not config.api_key:
            raise ValueError("Brave Search requires WEBGATE_BRAVE_API_KEY to be set")
        self._api_key = config.api_key
        self._safesearch = config.safesearch

    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "q": query,
            "count": min(num_results, 20),  # Brave API max is 20 per request
            "safesearch": ("off", "moderate", "strict")[min(self._safesearch, 2)],
        }
        if lang:
            params["search_lang"] = lang

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._BASE_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("web", {}).get("results", []):
            if len(results) >= num_results:
                break
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                )
            )
        return results
