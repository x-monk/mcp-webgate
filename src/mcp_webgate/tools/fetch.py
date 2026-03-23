"""MCP tool: fetch — retrieve and clean a single URL."""

from __future__ import annotations

import time

from ..config import Config
from ..scraper.cleaner import process_page
from ..scraper.fetcher import fetch_urls
from ..utils.logger import log_fetch
from ..utils.url import is_binary_url, is_domain_allowed, sanitize_url


async def tool_fetch(
    url: str,
    config: Config,
    max_chars: int | None = None,
) -> dict:
    """Fetch a single URL, clean, and return structured result."""
    t0 = time.monotonic()
    url = sanitize_url(url)
    effective_max = min(max_chars or config.server.max_query_budget, config.server.max_query_budget)

    if is_binary_url(url):
        log_fetch(url=url, raw_bytes=0, clean_chars=0, elapsed_ms=0, success=False)
        return {
            "url": url,
            "title": "",
            "text": "[Blocked: binary file extension]",
            "truncated": False,
            "char_count": 0,
        }

    if not is_domain_allowed(url, config.server.blocked_domains, config.server.allowed_domains):
        log_fetch(url=url, raw_bytes=0, clean_chars=0, elapsed_ms=0, success=False)
        return {
            "url": url,
            "title": "",
            "text": "[Blocked: domain not allowed]",
            "truncated": False,
            "char_count": 0,
        }

    html_map, _ = await fetch_urls(
        [url],
        max_bytes=config.server.max_download_bytes,
        timeout=config.server.search_timeout,
    )

    raw_html = html_map.get(url, "")
    elapsed_ms = (time.monotonic() - t0) * 1000

    if not raw_html:
        log_fetch(url=url, raw_bytes=0, clean_chars=0, elapsed_ms=elapsed_ms, success=False)
        return {
            "url": url,
            "title": "",
            "text": "[Fetch failed: no response or timeout]",
            "truncated": False,
            "char_count": 0,
        }

    text, title, truncated = process_page(raw_html, max_chars=effective_max)

    log_fetch(
        url=url,
        raw_bytes=len(raw_html.encode("utf-8", errors="replace")),
        clean_chars=len(text),
        elapsed_ms=elapsed_ms,
        success=True,
    )

    return {
        "url": url,
        "title": title,
        "text": text,
        "truncated": truncated,
        "char_count": len(text),
    }
