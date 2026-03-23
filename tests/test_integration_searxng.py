"""Integration tests with local SearXNG instance on port 4000.

These tests require a running SearXNG at http://localhost:4000.
They are skipped automatically if the service is not reachable.
"""

from __future__ import annotations

import httpx
import pytest

from mcp_webgate.backends.searxng import SearxngBackend
from mcp_webgate.config import Config, SearxngConfig
from mcp_webgate.tools.fetch import tool_fetch
from mcp_webgate.tools.query import tool_query

SEARXNG_URL = "http://localhost:4000"


def _searxng_available() -> bool:
    """Check if SearXNG is reachable."""
    try:
        resp = httpx.get(f"{SEARXNG_URL}/", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _searxng_available(),
    reason=f"SearXNG not available at {SEARXNG_URL}",
)


@pytest.fixture
def searxng_config() -> Config:
    cfg = Config()
    cfg.backends.searxng = SearxngConfig(url=SEARXNG_URL)
    cfg.backends.default = "searxng"
    cfg.server.max_result_length = 2000
    return cfg


@pytest.fixture
def searxng_backend(searxng_config: Config) -> SearxngBackend:
    return SearxngBackend(searxng_config.backends.searxng)


class TestSearxngBackend:
    async def test_search_returns_results(self, searxng_backend: SearxngBackend):
        results = await searxng_backend.search("python programming", 3)
        assert len(results) > 0
        for r in results:
            assert r.url
            assert r.title

    async def test_search_respects_num_results(self, searxng_backend: SearxngBackend):
        results = await searxng_backend.search("wikipedia", 2)
        assert len(results) <= 2


class TestFetchToolIntegration:
    async def test_fetch_real_page(self, searxng_config: Config):
        result = await tool_fetch("https://httpbin.org/html", searxng_config)
        assert result["url"] == "https://httpbin.org/html"
        assert result["char_count"] > 0
        assert result["text"]

    async def test_fetch_binary_blocked(self, searxng_config: Config):
        result = await tool_fetch("https://example.com/file.pdf", searxng_config)
        assert "Blocked" in result["text"]


class TestQueryToolIntegration:
    async def test_full_query_cycle(
        self,
        searxng_backend: SearxngBackend,
        searxng_config: Config,
    ):
        result = await tool_query(
            "python asyncio tutorial",
            backend=searxng_backend,
            config=searxng_config,
            num_results_per_query=3,
        )
        assert result["queries"] == "python asyncio tutorial"
        assert "sources" in result
        assert "stats" in result
        assert result["stats"]["fetched"] >= 0

    async def test_query_has_snippet_pool(
        self,
        searxng_backend: SearxngBackend,
        searxng_config: Config,
    ):
        result = await tool_query(
            "python requests library",
            backend=searxng_backend,
            config=searxng_config,
            num_results_per_query=2,
        )
        # With oversampling_factor=2, we request 4 results
        # so snippet_pool should have leftovers
        assert "snippet_pool" in result
