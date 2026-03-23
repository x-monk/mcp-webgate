"""Exa (neural) search backend.

Exa uses semantic/neural search by default, making it complementary to
keyword-based backends. autoprompt is always disabled because mcp-webgate
handles query expansion itself.
"""

from __future__ import annotations

import httpx

from ..config import ExaConfig
from .base import SearchBackend, SearchResult


class ExaBackend(SearchBackend):
    """Exa neural search backend. Requires an API key."""

    _BASE_URL = "https://api.exa.ai/search"

    def __init__(self, config: ExaConfig) -> None:
        if not config.api_key:
            raise ValueError("Exa Search requires WEBGATE_EXA_API_KEY to be set")
        self._config = config

    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        payload: dict = {
            "query": query,
            "numResults": min(num_results, 10),  # Exa free tier max is 10
            "useAutoprompt": False,  # mcp-webgate handles expansion
            "type": self._config.type,
            "contents": {
                "highlights": {
                    "numSentences": self._config.num_sentences,
                    "highlightsPerUrl": 1,
                },
            },
        }

        headers = {
            "x-api-key": self._config.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._BASE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("results", []):
            if len(results) >= num_results:
                break
            # Prefer highlights over raw text as snippet
            highlights = item.get("highlights", [])
            snippet = highlights[0] if highlights else item.get("text", "")
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=snippet,
                )
            )
        return results
