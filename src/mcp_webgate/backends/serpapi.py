"""SerpAPI backend.

SerpAPI acts as a proxy for multiple search engines (Google, Bing, DuckDuckGo,
Yandex, Yahoo). The `engine` config key selects which engine to use without
any code changes.
"""

from __future__ import annotations

import httpx

from ..config import SerpapiConfig
from .base import SearchBackend, SearchResult


class SerpapiBackend(SearchBackend):
    """SerpAPI backend. Requires an API key and supports multiple engines."""

    _BASE_URL = "https://serpapi.com/search"

    def __init__(self, config: SerpapiConfig) -> None:
        if not config.api_key:
            raise ValueError("SerpAPI requires WEBGATE_SERPAPI_API_KEY to be set")
        self._config = config

    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "api_key": self._config.api_key,
            "q": query,
            "engine": self._config.engine,
            "num": min(num_results, 100),
            "gl": self._config.gl,
            "hl": lang or self._config.hl,
            "safe": self._config.safe,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("organic_results", []):
            if len(results) >= num_results:
                break
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                )
            )
        return results
