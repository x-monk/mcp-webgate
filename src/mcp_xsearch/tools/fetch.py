"""MCP tool: fetch — retrieve and clean a single URL."""

from __future__ import annotations

from ..config import Config
from ..scraper.cleaner import process_page
from ..scraper.fetcher import fetch_urls
from ..utils.url import is_binary_url, sanitize_url


async def tool_fetch(
    url: str,
    config: Config,
    max_chars: int | None = None,
) -> dict:
    """Fetch a single URL, clean, and return structured result."""
    url = sanitize_url(url)
    effective_max = min(max_chars or config.server.max_result_length, config.server.max_result_length)

    if is_binary_url(url):
        return {
            "url": url,
            "title": "",
            "text": "[Blocked: binary file extension]",
            "truncated": False,
            "char_count": 0,
        }

    html_map = await fetch_urls(
        [url],
        max_bytes=config.server.max_download_bytes,
        timeout=config.server.search_timeout,
    )

    raw_html = html_map.get(url, "")
    if not raw_html:
        return {
            "url": url,
            "title": "",
            "text": "[Fetch failed: no response or timeout]",
            "truncated": False,
            "char_count": 0,
        }

    text, title, truncated = process_page(raw_html, max_chars=effective_max)

    return {
        "url": url,
        "title": title,
        "text": text,
        "truncated": truncated,
        "char_count": len(text),
    }
