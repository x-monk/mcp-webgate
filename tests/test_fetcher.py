"""Tests for the concurrent HTTP fetcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from mcp_webgate.scraper.fetcher import USER_AGENTS, _BACKOFF_DELAYS, _fetch_single, fetch_urls


class TestUserAgents:
    def test_agent_list_not_empty(self):
        assert len(USER_AGENTS) == 20

    def test_all_agents_are_strings(self):
        for ua in USER_AGENTS:
            assert isinstance(ua, str)
            assert "Mozilla" in ua


class TestFetchSingle:
    async def test_returns_html_on_success(self):
        body = b"<html><body>Hello</body></html>"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.encoding = "utf-8"
        mock_response.aiter_bytes = lambda: _async_iter([body])
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "fake_request"
        mock_client.send = AsyncMock(return_value=mock_response)

        html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "http://example.com", max_bytes=1_000_000)
        assert html == body.decode("utf-8")
        assert elapsed_ms >= 0
        assert raw_bytes == len(body)

    async def test_returns_none_on_non_200(self):
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "fake_request"
        mock_client.send = AsyncMock(return_value=mock_response)

        html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "http://example.com", max_bytes=1_000_000)
        assert html is None
        assert raw_bytes == 0

    async def test_truncates_at_max_bytes(self):
        chunk1 = b"A" * 500
        chunk2 = b"B" * 500
        chunk3 = b"C" * 500  # should be cut off

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.encoding = "utf-8"
        mock_response.aiter_bytes = lambda: _async_iter([chunk1, chunk2, chunk3])
        mock_response.aclose = AsyncMock()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "fake_request"
        mock_client.send = AsyncMock(return_value=mock_response)

        html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "http://example.com", max_bytes=800)
        # Should stop after chunk2 exceeds 800 bytes (500+500=1000 > 800)
        assert html is not None
        assert len(html) <= 1000

    async def test_returns_none_on_exception(self):
        mock_client = AsyncMock()
        mock_client.build_request.side_effect = Exception("Connection error")

        html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "http://example.com", max_bytes=1_000_000)
        assert html is None


class TestFetchUrls:
    async def test_empty_urls(self):
        html_map, timing_map = await fetch_urls([], max_bytes=1_000_000)
        assert html_map == {}
        assert timing_map == {}

    async def test_returns_dict_keyed_by_url(self):
        body = b"<html><body>Test</body></html>"

        async def _mock_send(req, stream=False):
            resp = MagicMock()
            resp.status_code = 200
            resp.encoding = "utf-8"
            resp.aiter_bytes = lambda: _async_iter([body])
            resp.aclose = AsyncMock()
            return resp

        with patch("mcp_webgate.scraper.fetcher.httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.build_request.return_value = "fake_request"
            instance.send = _mock_send
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            html_map, timing_map = await fetch_urls(["http://example.com"], max_bytes=1_000_000)
            assert "http://example.com" in html_map
            assert "Test" in html_map["http://example.com"]
            assert "http://example.com" in timing_map
            elapsed_ms, raw_bytes = timing_map["http://example.com"]
            assert elapsed_ms >= 0
            assert raw_bytes == len(body)


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


class TestRetryBackoff:
    def _make_response(self, status: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.headers = {}
        resp.aclose = AsyncMock()
        return resp

    def _make_success_response(self, body: bytes = b"<html>OK</html>") -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.encoding = "utf-8"
        resp.headers = {}
        resp.aiter_bytes = lambda: _async_iter([body])
        resp.aclose = AsyncMock()
        return resp

    async def test_retries_on_429_and_succeeds(self):
        """On 429, fetcher retries and returns content on next success."""
        fail = self._make_response(429)
        ok = self._make_success_response()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "req"
        mock_client.send = AsyncMock(side_effect=[fail, ok])

        with patch("mcp_webgate.scraper.fetcher.asyncio.sleep", new_callable=AsyncMock):
            html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "https://example.com", max_bytes=1_000_000)

        assert html is not None
        assert "OK" in html
        assert mock_client.send.call_count == 2

    async def test_retries_on_503(self):
        """503 Service Unavailable also triggers retry."""
        fail = self._make_response(503)
        ok = self._make_success_response()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "req"
        mock_client.send = AsyncMock(side_effect=[fail, ok])

        with patch("mcp_webgate.scraper.fetcher.asyncio.sleep", new_callable=AsyncMock):
            html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "https://example.com", max_bytes=1_000_000)

        assert html is not None

    async def test_exhausts_retries_returns_none(self):
        """After all retries return 429, result is None."""
        from mcp_webgate.scraper.fetcher import _BACKOFF_DELAYS

        responses = [self._make_response(429)] * (len(_BACKOFF_DELAYS) + 1)
        mock_client = AsyncMock()
        mock_client.build_request.return_value = "req"
        mock_client.send = AsyncMock(side_effect=responses)

        with patch("mcp_webgate.scraper.fetcher.asyncio.sleep", new_callable=AsyncMock):
            html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "https://example.com", max_bytes=1_000_000)

        assert html is None

    async def test_respects_retry_after_header(self):
        """Retry-After header value is used as the minimum sleep duration."""
        fail = self._make_response(429)
        fail.headers = {"retry-after": "5"}
        ok = self._make_success_response()

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "req"
        mock_client.send = AsyncMock(side_effect=[fail, ok])

        mock_sleep = AsyncMock()
        with patch("mcp_webgate.scraper.fetcher.asyncio.sleep", mock_sleep):
            await _fetch_single(mock_client, "https://example.com", max_bytes=1_000_000)

        # Sleep must be called with at least 5.0 (from Retry-After)
        assert mock_sleep.call_args[0][0] >= 5.0

    async def test_404_does_not_retry(self):
        """Non-retryable errors (404) fail immediately without retrying."""
        fail = self._make_response(404)

        mock_client = AsyncMock()
        mock_client.build_request.return_value = "req"
        mock_client.send = AsyncMock(return_value=fail)

        html, elapsed_ms, raw_bytes = await _fetch_single(mock_client, "https://example.com", max_bytes=1_000_000)

        assert html is None
        assert mock_client.send.call_count == 1
