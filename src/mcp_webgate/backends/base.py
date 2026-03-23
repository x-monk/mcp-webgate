"""Abstract search backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    """A single search result from a backend."""

    title: str
    url: str
    snippet: str


class SearchBackend(ABC):
    """Base class for search engine backends."""

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int,
        lang: str | None = None,
    ) -> list[SearchResult]:
        """Execute a search and return results."""
        ...
