"""Tests for search backends (Brave, Tavily, Exa, SerpAPI) using mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_webgate.backends.base import SearchResult
from mcp_webgate.backends.brave import BraveBackend
from mcp_webgate.backends.exa import ExaBackend
from mcp_webgate.backends.serpapi import SerpapiBackend
from mcp_webgate.backends.tavily import TavilyBackend
from mcp_webgate.config import BraveConfig, ExaConfig, SerpapiConfig, TavilyConfig


class TestBraveBackend:
    def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="WEBGATE_BRAVE_API_KEY"):
            BraveBackend(BraveConfig(api_key=""))

    def _make_brave_response(self, items: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"web": {"results": items}}
        return mock_resp

    async def test_search_returns_results(self):
        items = [
            {"title": "Result 1", "url": "https://example.com/1", "description": "Snippet 1"},
            {"title": "Result 2", "url": "https://example.com/2", "description": "Snippet 2"},
        ]
        mock_resp = self._make_brave_response(items)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.brave.httpx.AsyncClient", return_value=mock_cm):
            backend = BraveBackend(BraveConfig(api_key="test-key"))
            results = await backend.search("python", num_results=2)

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"

    async def test_search_respects_num_results(self):
        items = [
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "description": ""}
            for i in range(10)
        ]
        mock_resp = self._make_brave_response(items)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.brave.httpx.AsyncClient", return_value=mock_cm):
            backend = BraveBackend(BraveConfig(api_key="test-key"))
            results = await backend.search("test", num_results=3)

        assert len(results) == 3

    async def test_search_with_lang(self):
        mock_resp = self._make_brave_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.brave.httpx.AsyncClient", return_value=mock_cm):
            backend = BraveBackend(BraveConfig(api_key="test-key"))
            results = await backend.search("test", num_results=5, lang="it")

        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["params"]["search_lang"] == "it"

    async def test_empty_results(self):
        mock_resp = self._make_brave_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.brave.httpx.AsyncClient", return_value=mock_cm):
            backend = BraveBackend(BraveConfig(api_key="test-key"))
            results = await backend.search("test", num_results=5)

        assert results == []


class TestTavilyBackend:
    def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="WEBGATE_TAVILY_API_KEY"):
            TavilyBackend(TavilyConfig(api_key=""))

    def _make_tavily_response(self, items: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": items}
        return mock_resp

    async def test_search_returns_results(self):
        items = [
            {"title": "Result 1", "url": "https://example.com/1", "content": "Content 1"},
            {"title": "Result 2", "url": "https://example.com/2", "content": "Content 2"},
        ]
        mock_resp = self._make_tavily_response(items)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.tavily.httpx.AsyncClient", return_value=mock_cm):
            backend = TavilyBackend(TavilyConfig(api_key="test-key"))
            results = await backend.search("python", num_results=2)

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].snippet == "Content 1"

    async def test_search_respects_num_results(self):
        items = [
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": ""}
            for i in range(10)
        ]
        mock_resp = self._make_tavily_response(items)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.tavily.httpx.AsyncClient", return_value=mock_cm):
            backend = TavilyBackend(TavilyConfig(api_key="test-key"))
            results = await backend.search("test", num_results=4)

        assert len(results) == 4

    async def test_payload_uses_configured_search_depth(self):
        mock_resp = self._make_tavily_response([])
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.tavily.httpx.AsyncClient", return_value=mock_cm):
            backend = TavilyBackend(TavilyConfig(api_key="test-key", search_depth="advanced"))
            await backend.search("test", num_results=5)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["search_depth"] == "advanced"


class TestExaBackend:
    def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="WEBGATE_EXA_API_KEY"):
            ExaBackend(ExaConfig(api_key=""))

    def _make_exa_response(self, items: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": items}
        return mock_resp

    async def test_search_returns_results(self):
        items = [
            {"title": "Result 1", "url": "https://example.com/1", "highlights": ["Highlight 1"]},
            {"title": "Result 2", "url": "https://example.com/2", "highlights": ["Highlight 2"]},
        ]
        mock_resp = self._make_exa_response(items)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.exa.httpx.AsyncClient", return_value=mock_cm):
            backend = ExaBackend(ExaConfig(api_key="test-key"))
            results = await backend.search("semantic query", num_results=2)

        assert len(results) == 2
        assert results[0].snippet == "Highlight 1"
        assert results[1].snippet == "Highlight 2"

    async def test_uses_highlight_over_text(self):
        """Highlights are preferred as snippet; falls back to text if missing."""
        items = [
            {"title": "T1", "url": "https://example.com/1", "highlights": ["H1"], "text": "Full text"},
            {"title": "T2", "url": "https://example.com/2", "highlights": [], "text": "Fallback text"},
        ]
        mock_resp = self._make_exa_response(items)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.exa.httpx.AsyncClient", return_value=mock_cm):
            backend = ExaBackend(ExaConfig(api_key="test-key"))
            results = await backend.search("test", num_results=2)

        assert results[0].snippet == "H1"
        assert results[1].snippet == "Fallback text"

    async def test_autoprompt_always_disabled(self):
        """useAutoprompt must always be False in the request payload."""
        mock_resp = self._make_exa_response([])
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.exa.httpx.AsyncClient", return_value=mock_cm):
            backend = ExaBackend(ExaConfig(api_key="test-key"))
            await backend.search("test", num_results=5)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["useAutoprompt"] is False

    async def test_search_type_is_configurable(self):
        mock_resp = self._make_exa_response([])
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.exa.httpx.AsyncClient", return_value=mock_cm):
            backend = ExaBackend(ExaConfig(api_key="test-key", type="keyword"))
            await backend.search("test", num_results=5)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["type"] == "keyword"


class TestSerpapiBackend:
    def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="WEBGATE_SERPAPI_API_KEY"):
            SerpapiBackend(SerpapiConfig(api_key=""))

    def _make_serpapi_response(self, items: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"organic_results": items}
        return mock_resp

    async def test_search_returns_results(self):
        items = [
            {"title": "Result 1", "link": "https://example.com/1", "snippet": "Snippet 1"},
            {"title": "Result 2", "link": "https://example.com/2", "snippet": "Snippet 2"},
        ]
        mock_resp = self._make_serpapi_response(items)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.serpapi.httpx.AsyncClient", return_value=mock_cm):
            backend = SerpapiBackend(SerpapiConfig(api_key="test-key"))
            results = await backend.search("test", num_results=2)

        assert len(results) == 2
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"

    async def test_engine_is_configurable(self):
        mock_resp = self._make_serpapi_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.serpapi.httpx.AsyncClient", return_value=mock_cm):
            backend = SerpapiBackend(SerpapiConfig(api_key="test-key", engine="bing"))
            await backend.search("test", num_results=5)

        params = mock_client.get.call_args.kwargs["params"]
        assert params["engine"] == "bing"

    async def test_lang_overrides_hl(self):
        """The `lang` parameter passed to search() overrides the config's hl."""
        mock_resp = self._make_serpapi_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_webgate.backends.serpapi.httpx.AsyncClient", return_value=mock_cm):
            backend = SerpapiBackend(SerpapiConfig(api_key="test-key", hl="en"))
            await backend.search("test", num_results=5, lang="it")

        params = mock_client.get.call_args.kwargs["params"]
        assert params["hl"] == "it"


class TestSearxngBackend:
    def _make_response(self, items: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": items}
        return mock_resp

    async def test_search_returns_results(self):
        """search() maps SearXNG result fields to SearchResult correctly."""
        from mcp_webgate.backends.searxng import SearxngBackend
        from mcp_webgate.config import SearxngConfig

        backend = SearxngBackend(SearxngConfig(url="http://localhost:8888"))
        items = [
            {"title": "Result 1", "url": "https://example.com/1", "content": "Snippet 1"},
            {"title": "Result 2", "url": "https://example.com/2", "content": "Snippet 2"},
        ]
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=self._make_response(items))

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await backend.search("test query", 5)

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"

    async def test_search_respects_num_results(self):
        """search() caps the returned list at num_results."""
        from mcp_webgate.backends.searxng import SearxngBackend
        from mcp_webgate.config import SearxngConfig

        backend = SearxngBackend(SearxngConfig(url="http://localhost:8888"))
        items = [
            {"title": f"R{i}", "url": f"https://example.com/{i}", "content": "s"}
            for i in range(10)
        ]
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=self._make_response(items))

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await backend.search("test", 3)

        assert len(results) == 3

    async def test_search_with_lang_passes_language_param(self):
        """search() includes the language parameter when lang is specified."""
        from mcp_webgate.backends.searxng import SearxngBackend
        from mcp_webgate.config import SearxngConfig

        backend = SearxngBackend(SearxngConfig(url="http://localhost:8888"))
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=self._make_response([]))

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            await backend.search("query", 5, lang="it")

        _, call_kwargs = mock_client.get.call_args
        assert call_kwargs["params"]["language"] == "it"

    async def test_search_returns_empty_on_no_results(self):
        """search() returns an empty list when the API response has no results."""
        from mcp_webgate.backends.searxng import SearxngBackend
        from mcp_webgate.config import SearxngConfig

        backend = SearxngBackend(SearxngConfig(url="http://localhost:8888"))
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=self._make_response([]))

        with patch("httpx.AsyncClient") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            results = await backend.search("nothing", 5)

        assert results == []
