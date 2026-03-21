"""MCP tool: query — full search cycle with oversampling, cleaning, snippets."""

from __future__ import annotations

from ..backends.base import SearchBackend, SearchResult
from ..config import Config
from ..scraper.cleaner import process_page
from ..scraper.fetcher import fetch_urls
from ..utils.url import dedup_urls, is_binary_url, sanitize_url


async def tool_query(
    query: str,
    backend: SearchBackend,
    config: Config,
    num_results: int = 5,
    lang: str | None = None,
) -> dict:
    """Execute full search cycle: search → fetch → clean → assemble."""
    cfg = config.server

    # Clamp num_results
    num_results = min(num_results, cfg.max_total_results)

    # Oversample to guarantee signal density
    oversample_count = num_results * cfg.oversampling_factor
    raw_results = await backend.search(query, oversample_count, lang)

    # Filter and dedup
    valid: list[SearchResult] = []
    seen_urls: set[str] = set()
    for r in raw_results:
        clean = sanitize_url(r.url).lower().rstrip("/")
        if clean in seen_urls or is_binary_url(r.url):
            continue
        seen_urls.add(clean)
        valid.append(r)

    # Split into candidates (Round 1) and reserve pool
    candidates = valid[:num_results]
    reserve_pool = valid[num_results:]

    # Round 1: parallel fetch
    candidate_urls = [r.url for r in candidates]
    html_map = await fetch_urls(
        candidate_urls,
        max_bytes=cfg.max_download_bytes,
        timeout=cfg.search_timeout,
    )

    # Round 2: gap filler (replace failed fetches from reserve pool)
    if cfg.auto_recovery_fetch:
        failed = [r for r in candidates if r.url not in html_map]
        if failed and reserve_pool:
            gap_size = min(len(failed), len(reserve_pool))
            backups = reserve_pool[:gap_size]
            reserve_pool = reserve_pool[gap_size:]

            backup_urls = [r.url for r in backups]
            backup_html = await fetch_urls(
                backup_urls,
                max_bytes=cfg.max_download_bytes,
                timeout=cfg.search_timeout,
            )
            html_map.update(backup_html)

            # Rebuild candidates: keep successful, replace failed with backups
            new_candidates = [r for r in candidates if r.url in html_map]
            new_candidates.extend(backups)
            # Demote truly failed to reserve pool
            reserve_pool = [r for r in candidates if r.url not in html_map] + reserve_pool
            candidates = new_candidates

    # Process fetched pages
    sources: list[dict] = []
    fetched_count = 0
    failed_count = 0

    for idx, result in enumerate(candidates, 1):
        raw = html_map.get(result.url)
        if raw:
            text, title, truncated = process_page(
                raw, snippet=result.snippet, max_chars=cfg.max_result_length
            )
            fetched_count += 1
        else:
            text = result.snippet or "[Fetch failed]"
            title = result.title
            truncated = False
            failed_count += 1

        sources.append({
            "id": idx,
            "title": title or result.title,
            "url": result.url,
            "snippet": result.snippet,
            "content": text,
            "truncated": truncated,
        })

    # Snippet pool: unread pages from reserve
    snippet_pool = [
        {
            "id": len(sources) + i + 1,
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
        }
        for i, r in enumerate(reserve_pool)
    ]

    total_chars = sum(len(s["content"]) for s in sources)

    return {
        "query_used": query,
        "sources": sources,
        "snippet_pool": snippet_pool,
        "stats": {
            "fetched": fetched_count,
            "failed": failed_count,
            "gap_filled": len(candidates) - num_results if len(candidates) > num_results else 0,
            "total_chars": total_chars,
        },
    }
