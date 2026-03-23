"""Tests for tool_query: multi-query, round-robin merging, budget distribution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mcp_webgate.backends.base import SearchResult
from mcp_webgate.config import Config
from mcp_webgate.tools.query import tool_query


def _make_cfg(**kwargs) -> Config:
    cfg = Config()
    for k, v in kwargs.items():
        setattr(cfg.server, k, v)
    return cfg


def _results(prefix: str, n: int) -> list[SearchResult]:
    return [
        SearchResult(title=f"{prefix}{i}", url=f"https://{prefix}{i}.com", snippet="s")
        for i in range(n)
    ]


class TestSingleQuery:
    async def test_single_string_queries_field_is_string(self):
        """When one query is passed as str, output queries field is a plain string."""
        cfg = _make_cfg()
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title="T", url="https://example.com", snippet="S")
        ])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query("hello world", mock_backend, cfg, num_results_per_query=1)

        assert result["queries"] == "hello world"

    async def test_single_item_list_queries_field_is_string(self):
        """When a one-element list is passed, output queries is a plain string."""
        cfg = _make_cfg()
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title="T", url="https://example.com", snippet="S")
        ])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query(["hello world"], mock_backend, cfg, num_results_per_query=1)

        assert result["queries"] == "hello world"


class TestMultiQuery:
    async def test_list_queries_field_is_list(self):
        """When multiple queries are passed, output queries field is a list."""
        cfg = _make_cfg()
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title="T", url="https://example.com", snippet="S")
        ])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query(["q1", "q2"], mock_backend, cfg, num_results_per_query=1)

        assert result["queries"] == ["q1", "q2"]

    async def test_each_query_triggers_separate_backend_call(self):
        """Each query in the list fires a separate backend.search call."""
        cfg = _make_cfg()
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            await tool_query(["q1", "q2", "q3"], mock_backend, cfg, num_results_per_query=3)

        assert mock_backend.search.call_count == 3
        called_queries = {c.args[0] for c in mock_backend.search.call_args_list}
        assert called_queries == {"q1", "q2", "q3"}

    async def test_queries_capped_at_max_search_queries(self):
        """List longer than max_search_queries is silently truncated to server cap."""
        cfg = _make_cfg(max_search_queries=2)
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            await tool_query(["q1", "q2", "q3", "q4", "q5"], mock_backend, cfg, num_results_per_query=1)

        assert mock_backend.search.call_count == 2
        called_queries = {c.args[0] for c in mock_backend.search.call_args_list}
        assert called_queries == {"q1", "q2"}

    async def test_round_robin_merging(self):
        """Round-robin ensures both queries contribute results to the output."""
        cfg = _make_cfg(oversampling_factor=1)

        call_count = 0

        async def side_effect(q, num, lang):
            nonlocal call_count
            prefix = "a" if call_count == 0 else "b"
            call_count += 1
            return _results(prefix, 2)

        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(side_effect=side_effect)

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query(["q1", "q2"], mock_backend, cfg, num_results_per_query=4)

        all_urls = (
            [s["url"] for s in result["sources"]]
            + [s["url"] for s in result["snippet_pool"]]
        )
        # Both queries must be represented in the output (round-robin coverage guarantee).
        # Note: BM25 reranking may change the final order, but both queries must contribute.
        has_a = any("a" in u for u in all_urls)
        has_b = any("b" in u for u in all_urls)
        assert has_a and has_b, "Both queries must contribute results"
        assert len(set(all_urls)) == len(all_urls), "No duplicates"


class TestQueryBudget:
    async def test_per_page_limit_distributed_evenly(self):
        """per_page_limit = budget // num_results when below max_result_length."""
        cfg = _make_cfg(max_result_length=4000, max_query_budget=10000)

        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title=f"T{i}", url=f"https://example.com/{i}", snippet="S")
            for i in range(10)
        ])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=5)

        assert result["stats"]["per_page_limit"] == 2000

    async def test_per_page_limit_capped_at_max_result_length(self):
        """per_page_limit never exceeds max_result_length."""
        cfg = _make_cfg(max_result_length=4000, max_query_budget=100000)

        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title=f"T{i}", url=f"https://example.com/{i}", snippet="S")
            for i in range(4)
        ])

        with patch("mcp_webgate.tools.query.fetch_urls", return_value=({}, {})):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=2)

        assert result["stats"]["per_page_limit"] == 4000

    async def test_total_chars_bounded_by_budget(self):
        """Total chars in sources never exceeds max_query_budget."""
        cfg = _make_cfg(max_result_length=4000, max_query_budget=6000)

        urls = [f"https://example.com/{i}" for i in range(6)]
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title=f"T{i}", url=urls[i], snippet="S")
            for i in range(6)
        ])
        fake_html = {url: "<p>" + "x" * 3000 + "</p>" for url in urls[:3]}

        fake_timing = {url: (500.0, 3000) for url in fake_html}
        with patch("mcp_webgate.tools.query.fetch_urls", return_value=(fake_html, fake_timing)):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=3)

        assert result["stats"]["total_chars"] <= cfg.server.max_query_budget


class TestGapFiller:
    async def test_gap_filler_replaces_failed_urls(self):
        """Round-2 fetch fills slots for candidates that failed in Round 1."""
        cfg = _make_cfg(auto_recovery_fetch=True, max_total_results=20)
        mock_backend = AsyncMock()
        # 6 results: 4 become candidates, 2 go to reserve pool
        mock_backend.search = AsyncMock(return_value=_results("a", 6))

        call_count = 0

        async def fake_fetch(urls, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Round 1: only first candidate succeeds
                return {urls[0]: "<p>ok</p>"}, {urls[0]: (10.0, 100)}
            # Round 2: all backups succeed
            return {u: "<p>ok</p>" for u in urls}, {u: (10.0, 100) for u in urls}

        with patch("mcp_webgate.tools.query.fetch_urls", side_effect=fake_fetch):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=4)

        assert result["stats"]["gap_filled"] > 0

    async def test_gap_filler_disabled_leaves_failures_as_snippets(self):
        """When auto_recovery_fetch=False, failed fetches are not replaced from reserve."""
        cfg = _make_cfg(auto_recovery_fetch=False, max_total_results=20)
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=_results("b", 6))

        async def fake_fetch(urls, **kwargs):
            return {urls[0]: "<p>ok</p>"}, {urls[0]: (10.0, 100)}

        with patch("mcp_webgate.tools.query.fetch_urls", side_effect=fake_fetch):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=4)

        assert result["stats"]["gap_filled"] == 0


class TestQueryLLMPaths:
    async def test_summarization_returns_citations_only(self):
        """With summarization enabled, response has summary + citations and no raw sources."""
        cfg = _make_cfg()
        cfg.llm.enabled = True
        cfg.llm.summarization_enabled = True
        cfg.llm.expansion_enabled = False
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=_results("s", 2))

        with (
            patch("mcp_webgate.tools.query.fetch_urls", new=AsyncMock(return_value=({}, {}))),
            patch("mcp_webgate.llm.client.LLMClient"),
            patch(
                "mcp_webgate.llm.summarizer.summarize_results",
                new=AsyncMock(return_value="A great summary."),
            ),
        ):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=2)

        assert result.get("summary") == "A great summary."
        assert "citations" in result
        assert "sources" not in result

    async def test_summarization_error_falls_back_to_sources(self):
        """When summarization raises, response contains llm_summary_error + full sources."""
        cfg = _make_cfg()
        cfg.llm.enabled = True
        cfg.llm.summarization_enabled = True
        cfg.llm.expansion_enabled = False
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=_results("e", 2))

        with (
            patch("mcp_webgate.tools.query.fetch_urls", new=AsyncMock(return_value=({}, {}))),
            patch("mcp_webgate.llm.client.LLMClient"),
            patch(
                "mcp_webgate.llm.summarizer.summarize_results",
                new=AsyncMock(side_effect=RuntimeError("oops")),
            ),
        ):
            result = await tool_query("test", mock_backend, cfg, num_results_per_query=2)

        assert "llm_summary_error" in result
        assert "RuntimeError" in result["llm_summary_error"]
        assert "sources" in result

    async def test_llm_reranking_is_invoked(self):
        """When llm_rerank_enabled is True, rerank_llm is called in the pipeline."""
        cfg = _make_cfg()
        cfg.llm.enabled = True
        cfg.llm.llm_rerank_enabled = True
        cfg.llm.expansion_enabled = False
        cfg.llm.summarization_enabled = False
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=_results("r", 3))

        reranked = [
            {"id": i, "title": f"T{i}", "url": f"https://r{i}.com", "content": "", "truncated": False}
            for i in range(3)
        ]
        mock_rerank = AsyncMock(return_value=reranked)

        with (
            patch("mcp_webgate.tools.query.fetch_urls", new=AsyncMock(return_value=({}, {}))),
            patch("mcp_webgate.llm.client.LLMClient"),
            patch("mcp_webgate.tools.query.rerank_llm", new=mock_rerank),
        ):
            await tool_query("test", mock_backend, cfg, num_results_per_query=3)

        mock_rerank.assert_called_once()


class TestQueryTrace:
    async def test_trace_output_includes_all_fields(self):
        """trace=True returns queries, stats, sources, and snippet_pool."""
        cfg = _make_cfg()
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=_results("t", 3))

        with patch("mcp_webgate.tools.query.fetch_urls", new=AsyncMock(return_value=({}, {}))):
            result = await tool_query(
                "trace-query", mock_backend, cfg, num_results_per_query=2, trace=True
            )

        assert result["queries"] == "trace-query"
        assert "sources" in result
        assert "snippet_pool" in result
        assert "stats" in result


class TestQueryDomainBlocking:
    async def test_blocked_domains_excluded_from_fetch(self):
        """Results from blocked domains are dropped before the fetch stage."""
        cfg = _make_cfg(blocked_domains=["blocked.com"])
        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title="OK", url="https://ok.com/page", snippet="s"),
            SearchResult(title="Bad", url="https://blocked.com/page", snippet="s"),
        ])

        mock_fetch = AsyncMock(return_value=({}, {}))
        with patch("mcp_webgate.tools.query.fetch_urls", mock_fetch):
            await tool_query("test", mock_backend, cfg, num_results_per_query=5)

        called_urls = mock_fetch.call_args[0][0]
        assert not any("blocked.com" in u for u in called_urls)
        assert any("ok.com" in u for u in called_urls)
