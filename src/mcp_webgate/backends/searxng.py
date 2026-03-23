"""SearXNG search backend."""

from __future__ import annotations

import httpx

from ..config import SearxngConfig
from .base import SearchBackend, SearchResult


class SearxngBackend(SearchBackend):
    """Self-hosted SearXNG instance backend."""

    def __init__(self, config: SearxngConfig) -> None:
        self._base_url = config.url.rstrip("/")

    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "pageno": 1,
        }
        if lang:
            params["language"] = lang

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._base_url}/search", params=params)
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
