"""Unit tests for tool_fetch: binary blocking, domain blocking, fetch failure, success."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from mcp_webgate.config import Config
from mcp_webgate.tools.fetch import tool_fetch


def _cfg(**kwargs) -> Config:
    cfg = Config()
    for k, v in kwargs.items():
        setattr(cfg.server, k, v)
    return cfg


class TestToolFetch:
    async def test_binary_url_blocked(self):
        """Binary URLs (e.g. .pdf) are rejected before any network call."""
        cfg = _cfg()
        result = await tool_fetch("https://example.com/report.pdf", cfg)
        assert "Blocked" in result["text"]
        assert result["char_count"] == 0
        assert result["truncated"] is False

    async def test_domain_blocked(self):
        """URLs from blocked domains return a domain-blocked message without fetching."""
        cfg = _cfg(blocked_domains=["evil.com"])
        result = await tool_fetch("https://evil.com/page", cfg)
        assert "Blocked" in result["text"]
        assert result["char_count"] == 0

    async def test_fetch_failure_returns_error_message(self):
        """When fetch_urls returns no HTML, the result carries a failure message."""
        cfg = _cfg()
        with patch("mcp_webgate.tools.fetch.fetch_urls", new=AsyncMock(return_value=({}, {}))):
            result = await tool_fetch("https://example.com/page", cfg)
        assert "Fetch failed" in result["text"]
        assert result["char_count"] == 0
        assert result["truncated"] is False

    async def test_successful_fetch_returns_cleaned_text(self):
        """A successful fetch returns cleaned text, a title, and char_count > 0."""
        cfg = _cfg()
        url = "https://example.com/page"
        html = (
            "<html><head><title>Hello Page</title></head>"
            "<body><p>World content here.</p></body></html>"
        )
        fake_map = {url: html}
        fake_timing = {url: (50.0, len(html))}
        with patch(
            "mcp_webgate.tools.fetch.fetch_urls",
            new=AsyncMock(return_value=(fake_map, fake_timing)),
        ):
            result = await tool_fetch(url, cfg)
        assert result["char_count"] > 0
        assert "World content" in result["text"]
        assert result["title"] == "Hello Page"
        assert result["url"] == url

    async def test_max_chars_caps_output(self):
        """max_chars parameter limits the output content length."""
        cfg = _cfg()
        url = "https://example.com/page"
        html = "<p>" + "word " * 5000 + "</p>"
        fake_map = {url: html}
        fake_timing = {url: (10.0, len(html))}
        with patch(
            "mcp_webgate.tools.fetch.fetch_urls",
            new=AsyncMock(return_value=(fake_map, fake_timing)),
        ):
            result = await tool_fetch(url, cfg, max_chars=200)
        assert result["char_count"] <= 200
