"""Concurrent HTTP fetcher with streaming, size cap, UA rotation, and retry backoff."""

from __future__ import annotations

import asyncio
import random
import time

import httpx

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/117.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Vivaldi/6.6.3271.45",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# HTTP status codes that warrant a retry with backoff
_RETRYABLE_STATUSES = {429, 502, 503}

# Backoff delays in seconds for each retry attempt (index = attempt number, 0-based)
_BACKOFF_DELAYS = [1.0, 2.5]


def _retry_after(response: httpx.Response) -> float:
    """Parse the Retry-After header if present, else return 0."""
    value = response.headers.get("retry-after", "")
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


async def _fetch_single(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
) -> tuple[str | None, float, int]:
    """Fetch a single URL with streaming, size cap, and retry backoff.

    Returns (html | None, elapsed_ms, raw_bytes).

    On 429/502/503, retries up to len(_BACKOFF_DELAYS) times with increasing
    delays. A fresh User-Agent is picked on each attempt to reduce fingerprinting.
    """
    t0 = time.monotonic()
    raw_bytes = 0
    for attempt in range(len(_BACKOFF_DELAYS) + 1):
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            req = client.build_request("GET", url, headers=headers)
            response = await client.send(req, stream=True)

            if response.status_code in _RETRYABLE_STATUSES:
                await response.aclose()
                if attempt < len(_BACKOFF_DELAYS):
                    delay = max(_retry_after(response), _BACKOFF_DELAYS[attempt])
                    await asyncio.sleep(delay)
                    continue
                return None, (time.monotonic() - t0) * 1000, raw_bytes

            if response.status_code != 200:
                await response.aclose()
                return None, (time.monotonic() - t0) * 1000, raw_bytes

            # Stream to enforce max_download_mb cap — DO NOT switch to client.get()
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    await response.aclose()
                    break

            await response.aclose()
            raw_bytes = len(body)
            encoding = response.encoding or "utf-8"
            return body.decode(encoding, errors="replace"), (time.monotonic() - t0) * 1000, raw_bytes

        except Exception:
            return None, (time.monotonic() - t0) * 1000, raw_bytes

    return None, (time.monotonic() - t0) * 1000, raw_bytes  # exhausted retries


async def fetch_urls(
    urls: list[str],
    max_bytes: int,
    timeout: float = 8.0,
) -> tuple[dict[str, str], dict[str, tuple[float, int]]]:
    """Fetch multiple URLs concurrently.

    Returns:
        (html_map, timing_map) where:
        - html_map:    {url: html} for successful fetches only
        - timing_map:  {url: (elapsed_ms, raw_bytes)} for all attempted fetches
    """
    if not urls:
        return {}, {}

    http_timeout = httpx.Timeout(timeout, connect=5.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(
        timeout=http_timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        tasks = [_fetch_single(client, url, max_bytes) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    html_map: dict[str, str] = {}
    timing_map: dict[str, tuple[float, int]] = {}
    for url, result in zip(urls, responses):
        if isinstance(result, tuple):
            html, elapsed_ms, raw_bytes = result
            timing_map[url] = (elapsed_ms, raw_bytes)
            if isinstance(html, str):
                html_map[url] = html
    return html_map, timing_map
