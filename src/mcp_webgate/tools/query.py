"""MCP tool: query — full search cycle with oversampling, cleaning, snippets."""

from __future__ import annotations

import asyncio
import time

from ..backends.base import SearchBackend, SearchResult
from ..config import Config
from ..scraper.cleaner import process_page
from ..scraper.fetcher import fetch_urls
from ..utils.logger import log_query
from ..utils.reranker import rerank_deterministic, rerank_llm, rerank_with_scores
from ..utils.url import dedup_urls, is_binary_url, is_domain_allowed, sanitize_url


async def tool_query(
    queries: str | list[str],
    backend: SearchBackend,
    config: Config,
    num_results_per_query: int = 5,
    lang: str | None = None,
    *,
    trace: bool = False,
) -> dict:
    """Execute full search cycle: search → fetch → clean → rerank → assemble → (summarize).

    num_results_per_query controls how many results to fetch *per query*.
    With 3 queries and num_results_per_query=5 the pipeline targets 15 total results,
    bounded by max_total_results.
    Summarization and query expansion are controlled entirely by config (llm.enabled,
    llm.summarization_enabled, llm.expansion_enabled).
    num_results_per_query defaults to config.server.results_per_query when not specified.
    """
    t0 = time.monotonic()
    cfg = config.server
    llm_cfg = config.llm

    # Clamp per-query limit to the global cap (avoids a single-query call bypassing it)
    num_results_per_query = min(num_results_per_query, cfg.max_total_results)

    # Normalize queries to list, enforce server cap
    if isinstance(queries, str):
        queries_list = [queries]
    else:
        queries_list = list(queries)[: cfg.max_search_queries]

    # LLM query expansion: if LLM is enabled, only one query provided, and expansion
    # is enabled — generate complementary queries automatically.
    if llm_cfg.enabled and llm_cfg.expansion_enabled and len(queries_list) == 1:
        from ..llm.client import LLMClient
        from ..llm.expander import expand_queries
        _client = LLMClient(llm_cfg)
        queries_list = await expand_queries(queries_list[0], cfg.max_search_queries, _client)

    t1 = time.monotonic()  # after expansion

    query_used = queries_list[0] if len(queries_list) == 1 else queries_list

    # Total candidates = per-query × number of queries, hard-capped at max_total_results.
    # Example: 3 queries × 5 results = 15, bounded by max_total_results (default 20).
    total_results = min(num_results_per_query * len(queries_list), cfg.max_total_results)

    # Oversample per query to guarantee signal density even after cross-query dedup.
    # All queries run in parallel via asyncio.gather — this is why we use httpx.
    oversample_count = num_results_per_query * cfg.oversampling_factor
    search_tasks = [backend.search(q, oversample_count, lang) for q in queries_list]
    results_per_query = await asyncio.gather(*search_tasks, return_exceptions=True)

    t2 = time.monotonic()  # after search

    # Flatten results from all queries in round-robin order so no single query
    # dominates the candidate pool (q1[0], q2[0], q3[0], q1[1], q2[1], ...)
    # Track which query each URL came from for per-query debug grouping.
    raw_results: list[SearchResult] = []
    result_lists = []
    result_list_qidx = []
    for i, r in enumerate(results_per_query):
        if isinstance(r, list):
            result_lists.append(r)
            result_list_qidx.append(i)

    url_to_query_idx: dict[str, int] = {}
    for i in range(max((len(r) for r in result_lists), default=0)):
        for list_pos, lst in enumerate(result_lists):
            if i < len(lst):
                r = lst[i]
                raw_results.append(r)
                if r.url not in url_to_query_idx:
                    url_to_query_idx[r.url] = result_list_qidx[list_pos]

    # Filter and dedup
    valid: list[SearchResult] = []
    seen_urls: set[str] = set()
    for r in raw_results:
        clean = sanitize_url(r.url).lower().rstrip("/")
        if clean in seen_urls or is_binary_url(r.url):
            continue
        if not is_domain_allowed(r.url, cfg.blocked_domains, cfg.allowed_domains):
            continue
        seen_urls.add(clean)
        valid.append(r)

    # Split into candidates (Round 1) and reserve pool
    candidates = valid[:total_results]
    reserve_pool = valid[total_results:]

    # Round 1: parallel fetch
    candidate_urls = [r.url for r in candidates]
    html_map, fetch_timing = await fetch_urls(
        candidate_urls,
        max_bytes=cfg.max_download_bytes,
        timeout=cfg.search_timeout,
    )

    # Round 2: gap filler (replace failed fetches from reserve pool)
    gap_filled = 0
    if cfg.auto_recovery_fetch:
        failed = [r for r in candidates if r.url not in html_map]
        if failed and reserve_pool:
            gap_size = min(len(failed), len(reserve_pool))
            backups = reserve_pool[:gap_size]
            reserve_pool = reserve_pool[gap_size:]

            backup_urls = [r.url for r in backups]
            backup_html, backup_timing = await fetch_urls(
                backup_urls,
                max_bytes=cfg.max_download_bytes,
                timeout=cfg.search_timeout,
            )
            html_map.update(backup_html)
            fetch_timing.update(backup_timing)

            # Rebuild candidates: keep successful, replace failed with backups
            new_candidates = [r for r in candidates if r.url in html_map]
            new_candidates.extend(backups)
            # Demote truly failed to reserve pool
            reserve_pool = [r for r in candidates if r.url not in html_map] + reserve_pool
            candidates = new_candidates
            gap_filled = len(backups)

    t3 = time.monotonic()  # after fetch (both rounds)

    # Per-page char limit.
    # Without summarization: distribute max_query_budget across candidates so the
    # raw output stays within the context budget for the invoking model.
    # With summarization: the LLM compresses input -> use a larger input pool
    # (max_query_budget × input_budget_factor, default 3×) distributed across
    # candidates. No hard per-page cap: the total is the guardian.
    will_summarize = llm_cfg.enabled and llm_cfg.summarization_enabled
    if will_summarize:
        llm_total = int(cfg.max_query_budget * llm_cfg.input_budget_factor)
        total_budget = llm_total
        per_page_limit = llm_total // max(1, len(candidates))
    else:
        total_budget = cfg.max_query_budget
        per_page_limit = min(
            cfg.max_result_length,
            cfg.max_query_budget // max(1, len(candidates)),
        )

    # EXPERIMENTAL — adaptive_budget: use a generous first-pass limit so the
    # reranker has rich signal; budget is redistributed proportionally after ranking.
    if cfg.adaptive_budget:
        fetch_limit = cfg.max_result_length * cfg.adaptive_budget_fetch_factor
    else:
        fetch_limit = per_page_limit

    # Process fetched pages — build fetch_details alongside for debug logging
    sources: list[dict] = []
    fetch_details: list[tuple[str, float, int, int, bool, int]] = []  # (url, ms, raw_b, clean_chars, ok, query_idx)
    fetched_count = 0
    failed_count = 0
    raw_bytes_total = 0

    for idx, result in enumerate(candidates, 1):
        raw = html_map.get(result.url)
        url_elapsed_ms, url_raw_bytes = fetch_timing.get(result.url, (0.0, 0))
        qi = url_to_query_idx.get(result.url, 0)
        if raw:
            raw_bytes_total += len(raw.encode("utf-8", errors="replace"))
            text, title, truncated = process_page(
                raw, snippet=result.snippet, max_chars=fetch_limit
            )
            fetched_count += 1
            fetch_details.append((result.url, url_elapsed_ms, url_raw_bytes, len(text), True, qi))
        else:
            text = result.snippet or "[Fetch failed]"
            title = result.title
            truncated = False
            failed_count += 1
            fetch_details.append((result.url, url_elapsed_ms, url_raw_bytes, 0, False, qi))

        entry: dict = {
            "id": idx,
            "title": title or result.title,
            "url": result.url,
            "content": text,
            "truncated": truncated,
        }
        # Only include snippet when it differs from content (avoid redundancy)
        if result.snippet and result.snippet != text:
            entry["snippet"] = result.snippet
        sources.append(entry)

    # Tier-1 rerank: deterministic BM25 — always active, zero cost.
    # EXPERIMENTAL adaptive_budget: use scored variant to proportionally redistribute
    # the char budget; top-ranked sources receive more chars, low-ranked sources less.
    if cfg.adaptive_budget:
        bm25_scores, sources = rerank_with_scores(queries_list, sources)
        total_score = sum(bm25_scores)
        if total_score > 0:
            allocs = [
                max(200, min(fetch_limit, int(s / total_score * total_budget)))
                for s in bm25_scores
            ]
        else:
            allocs = [total_budget // max(1, len(sources))] * len(sources)
        initial_allocs = list(allocs)  # snapshot before redistribution

        # Surplus redistribution: reclaim budget from sources whose actual
        # content is shorter than their allocation and give it to sources
        # that are still capped.  Iterate until no surplus remains or no
        # hungry source can absorb more.
        for _round in range(5):  # converges fast, cap to avoid edge-case loops
            surplus = 0
            hungry_indices: list[int] = []
            for i, (src, alloc) in enumerate(zip(sources, allocs)):
                actual = len(src["content"])
                if actual < alloc:
                    surplus += alloc - actual
                    allocs[i] = actual  # shrink alloc to actual
                elif actual > alloc:
                    hungry_indices.append(i)
            if surplus == 0 or not hungry_indices:
                break
            # Distribute surplus proportionally to BM25 scores of hungry sources
            hungry_score = sum(bm25_scores[i] for i in hungry_indices)
            if hungry_score <= 0:
                share = surplus // len(hungry_indices)
                for i in hungry_indices:
                    allocs[i] += share
            else:
                for i in hungry_indices:
                    allocs[i] += int(bm25_scores[i] / hungry_score * surplus)

        # Now truncate content to final allocations
        for source, alloc in zip(sources, allocs):
            if len(source["content"]) > alloc:
                source["content"] = source["content"][:alloc]
                source["truncated"] = True
        if cfg.trace:
            from ..utils.logger import log_adaptive_budget
            log_adaptive_budget(
                sources=sources,
                bm25_scores=bm25_scores,
                initial_allocs=initial_allocs,
                allocs=allocs,
                total_budget=total_budget,
                fetch_limit=fetch_limit,
            )
    else:
        sources = rerank_deterministic(queries_list, sources)

    # Tier-2 rerank: LLM-assisted — opt-in.
    # When adaptive_budget is active, this reorders already-allocated sources;
    # it changes presentation order but does not alter per-source char counts.
    if llm_cfg.enabled and llm_cfg.llm_rerank_enabled:
        from ..llm.client import LLMClient
        _rerank_client = LLMClient(llm_cfg)
        sources = await rerank_llm(queries_list, sources, _rerank_client)

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

    # Optional LLM summarization — appends a `summary` field to the response.
    # Activated entirely by config: llm.enabled + llm.summarization_enabled.
    # Sources are already bounded by max_result_length / max_query_budget,
    # so the summarizer receives them as-is without additional truncation.
    summary: str | None = None
    summary_error: str | None = None
    if llm_cfg.enabled and llm_cfg.summarization_enabled:
        from ..llm.client import LLMClient
        from ..llm.summarizer import summarize_results
        _sum_client = LLMClient(llm_cfg)
        max_words = llm_cfg.max_summary_words or cfg.max_query_budget // 5
        try:
            summary = await summarize_results(
                queries_list,
                sources,
                _sum_client,
                max_words=max_words,
            )
        except Exception as exc:
            msg = str(exc)
            summary_error = f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__

    t_end = time.monotonic()

    log_query(
        queries=queries_list,
        num_requested=total_results,
        fetched=fetched_count,
        failed=failed_count,
        gap_filled=gap_filled,
        raw_bytes_total=raw_bytes_total,
        clean_chars_total=total_chars,
        elapsed_ms=(t_end - t0) * 1000,
        expansion_ms=(t1 - t0) * 1000,
        search_ms=(t2 - t1) * 1000,
        fetch_ms=(t3 - t2) * 1000,
        fetch_details=fetch_details,
        summary_chars=len(summary) if summary else 0,
    )

    stats: dict = {
        "fetched": fetched_count,
        "failed": failed_count,
        "gap_filled": gap_filled,
        "total_chars": total_chars,
        "per_page_limit": per_page_limit,
        "num_results_per_query": num_results_per_query,
    }

    # trace: return everything for analysis — summary (or error) + full source content
    if trace:
        result: dict = {"queries": query_used, "stats": stats}
        if summary is not None:
            result["summary"] = summary
        elif summary_error is not None:
            result["llm_summary_error"] = summary_error
        result["sources"] = sources
        result["snippet_pool"] = snippet_pool
        return result

    # LLM summarization failed — return error reason + full sources as fallback
    if summary_error is not None:
        return {
            "queries": query_used,
            "llm_summary_error": summary_error,
            "sources": sources,
            "snippet_pool": snippet_pool,
            "stats": stats,
        }

    # When summarization produced a result, return a lean response:
    # summary + citations only — no raw content, no snippet pool.
    # This is the default behaviour when llm.summarization_enabled is true.
    if summary:
        citations = [
            {"id": s["id"], "title": s["title"], "url": s["url"]}
            for s in sources
        ]
        return {
            "queries": query_used,
            "summary": summary,
            "citations": citations,
            "stats": stats,
        }

    # No summarization — full response with content and snippet pool
    return {
        "queries": query_used,
        "sources": sources,
        "snippet_pool": snippet_pool,
        "stats": stats,
    }
