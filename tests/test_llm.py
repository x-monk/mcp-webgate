"""Unit tests for Phase 4 LLM features: client, expander, summarizer, reranker.

All tests are mock-based — no live API calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_webgate.config import LLMConfig
from mcp_webgate.llm.client import LLMClient
from mcp_webgate.llm.expander import expand_queries
from mcp_webgate.llm.summarizer import summarize_results
from mcp_webgate.utils.reranker import rerank_deterministic, rerank_llm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def llm_cfg() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        base_url="http://localhost:11434/v1",
        api_key="",
        model="llama3.2",
        timeout=5.0,
    )


@pytest.fixture
def client(llm_cfg: LLMConfig) -> LLMClient:
    return LLMClient(llm_cfg)


def _sources(n: int = 3) -> list[dict]:
    return [
        {
            "id": i + 1,
            "title": f"Title {i + 1}",
            "url": f"https://example.com/{i + 1}",
            "snippet": f"Snippet about topic {i + 1}",
            "content": f"Content about topic {i + 1} with some relevant keywords",
            "truncated": False,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class TestLLMClient:
    @pytest.mark.asyncio
    async def test_chat_success(self, client: LLMClient) -> None:
        """chat() returns the response text on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hello world"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_chat_raises_when_disabled(self) -> None:
        """chat() raises RuntimeError when LLM is not enabled."""
        cfg = LLMConfig(enabled=False)
        c = LLMClient(cfg)
        with pytest.raises(RuntimeError, match="not enabled"):
            await c.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_sends_correct_payload(self, client: LLMClient) -> None:
        """chat() sends model, messages, and temperature in the request body."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        post_mock = AsyncMock(return_value=mock_response)
        mock_instance = MagicMock()
        mock_instance.post = post_mock

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
            await client.chat([{"role": "user", "content": "test"}], temperature=0.5)

        _, kwargs = post_mock.call_args
        payload = kwargs["json"]
        assert payload["model"] == "llama3.2"
        assert payload["temperature"] == 0.5
        assert payload["messages"] == [{"role": "user", "content": "test"}]


# ---------------------------------------------------------------------------
# expand_queries
# ---------------------------------------------------------------------------

class TestExpandQueries:
    @pytest.mark.asyncio
    async def test_expand_success(self, client: LLMClient) -> None:
        """expand_queries returns original + generated variants."""
        client.chat = AsyncMock(return_value='["python concurrency", "asyncio vs threads"]')  # type: ignore[method-assign]
        result = await expand_queries("python async", 3, client)
        assert result[0] == "python async"
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_expand_fallback_on_json_error(self, client: LLMClient) -> None:
        """expand_queries returns [query] when LLM returns invalid JSON."""
        client.chat = AsyncMock(return_value="not valid json")  # type: ignore[method-assign]
        result = await expand_queries("python async", 3, client)
        assert result == ["python async"]

    @pytest.mark.asyncio
    async def test_expand_fallback_on_exception(self, client: LLMClient) -> None:
        """expand_queries returns [query] when LLM call raises."""
        client.chat = AsyncMock(side_effect=Exception("timeout"))  # type: ignore[method-assign]
        result = await expand_queries("python async", 3, client)
        assert result == ["python async"]

    @pytest.mark.asyncio
    async def test_expand_n1_skips_llm(self, client: LLMClient) -> None:
        """expand_queries with n=1 returns immediately without calling the LLM."""
        client.chat = AsyncMock()  # type: ignore[method-assign]
        result = await expand_queries("python async", 1, client)
        assert result == ["python async"]
        client.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_expand_strips_markdown_fences(self, client: LLMClient) -> None:
        """expand_queries handles JSON wrapped in markdown code fences."""
        client.chat = AsyncMock(return_value='```json\n["variant a", "variant b"]\n```')  # type: ignore[method-assign]
        result = await expand_queries("base query", 3, client)
        assert result[0] == "base query"
        assert "variant a" in result


# ---------------------------------------------------------------------------
# summarize_results
# ---------------------------------------------------------------------------

class TestSummarizeResults:
    @pytest.mark.asyncio
    async def test_summarize_success(self, client: LLMClient) -> None:
        """summarize_results returns the LLM-generated summary."""
        client.chat = AsyncMock(return_value="This is a summary [1][2].")  # type: ignore[method-assign]
        result = await summarize_results("test query", _sources(2), client)
        assert result == "This is a summary [1][2]."

    @pytest.mark.asyncio
    async def test_summarize_raises_on_error(self, client: LLMClient) -> None:
        """summarize_results propagates LLM errors to the caller."""
        client.chat = AsyncMock(side_effect=Exception("api error"))  # type: ignore[method-assign]
        with pytest.raises(Exception, match="api error"):
            await summarize_results("test query", _sources(2), client)

    @pytest.mark.asyncio
    async def test_summarize_includes_all_sources(self, client: LLMClient) -> None:
        """summarize_results includes all sources in the prompt and respects max_words."""
        captured: list[str] = []

        async def _capture(messages: list[dict], **_) -> str:
            captured.append(messages[0]["content"])
            return "summary"

        client.chat = _capture  # type: ignore[method-assign]
        sources = _sources(5)
        await summarize_results("q", sources, client, max_words=6400)
        prompt = captured[0]
        for s in sources:
            assert f"[{s['id']}]" in prompt
        assert "6400 words" in prompt


# ---------------------------------------------------------------------------
# rerank_deterministic
# ---------------------------------------------------------------------------

class TestRerankDeterministic:
    def test_orders_by_relevance(self) -> None:
        """BM25 reranker places the most relevant source first."""
        sources = [
            {"id": 1, "title": "Cooking recipes", "snippet": "pasta food",
             "content": "pasta pizza italian food"},
            {"id": 2, "title": "Python asyncio guide", "snippet": "async python",
             "content": "asyncio coroutine event loop python"},
        ]
        result = rerank_deterministic("python asyncio", sources)
        assert result[0]["id"] == 2

    def test_single_source_unchanged(self) -> None:
        """Single source list returned as-is."""
        sources = [{"id": 1, "title": "T", "snippet": "", "content": "x"}]
        assert rerank_deterministic("query", sources) == sources

    def test_empty_unchanged(self) -> None:
        """Empty list returned as-is."""
        assert rerank_deterministic("query", []) == []

    def test_accepts_list_query(self) -> None:
        """rerank_deterministic accepts list[str] queries."""
        sources = [
            {"id": 1, "title": "Alpha", "snippet": "alpha beta", "content": "alpha beta gamma"},
            {"id": 2, "title": "Delta", "snippet": "delta epsilon", "content": "delta epsilon zeta"},
        ]
        result = rerank_deterministic(["alpha", "beta"], sources)
        assert result[0]["id"] == 1

    def test_does_not_mutate_input(self) -> None:
        """rerank_deterministic does not mutate the input list."""
        sources = _sources(3)
        original_ids = [s["id"] for s in sources]
        rerank_deterministic("some query", sources)
        assert [s["id"] for s in sources] == original_ids


# ---------------------------------------------------------------------------
# rerank_llm
# ---------------------------------------------------------------------------

class TestRerankLLM:
    @pytest.mark.asyncio
    async def test_reorders_by_llm_ranking(self, client: LLMClient) -> None:
        """rerank_llm reorders sources according to the LLM-returned ID list."""
        sources = _sources(3)
        client.chat = AsyncMock(return_value="[3, 1, 2]")  # type: ignore[method-assign]
        result = await rerank_llm("query", sources, client)
        assert [s["id"] for s in result] == [3, 1, 2]

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self, client: LLMClient) -> None:
        """rerank_llm returns original order when LLM raises."""
        sources = _sources(3)
        client.chat = AsyncMock(side_effect=Exception("timeout"))  # type: ignore[method-assign]
        result = await rerank_llm("query", sources, client)
        assert [s["id"] for s in result] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, client: LLMClient) -> None:
        """rerank_llm returns original order when LLM returns invalid JSON."""
        sources = _sources(3)
        client.chat = AsyncMock(return_value="not json")  # type: ignore[method-assign]
        result = await rerank_llm("query", sources, client)
        assert [s["id"] for s in result] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_appends_omitted_sources(self, client: LLMClient) -> None:
        """Sources omitted by the LLM are appended at the end."""
        sources = _sources(3)
        client.chat = AsyncMock(return_value="[2]")  # type: ignore[method-assign]
        result = await rerank_llm("query", sources, client)
        assert result[0]["id"] == 2
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_single_source_unchanged(self, client: LLMClient) -> None:
        """Single source returned without calling the LLM."""
        sources = _sources(1)
        client.chat = AsyncMock()  # type: ignore[method-assign]
        result = await rerank_llm("query", sources, client)
        assert result == sources
        client.chat.assert_not_called()


class TestRerankWithScores:
    def test_returns_scores_and_reordered_sources(self):
        """Returns (scores, sources) with the most relevant source ranked first."""
        from mcp_webgate.utils.reranker import rerank_with_scores

        sources = [
            {"id": 1, "title": "Python tutorial", "content": "Learn Python basics"},
            {"id": 2, "title": "Cooking guide", "content": "How to cook pasta"},
        ]
        scores, reordered = rerank_with_scores("python programming", sources)
        assert len(scores) == 2
        assert len(reordered) == 2
        assert reordered[0]["id"] == 1
        assert scores[0] >= scores[1]

    def test_single_source_returns_score_one(self):
        """A single source is returned unchanged with score 1.0."""
        from mcp_webgate.utils.reranker import rerank_with_scores

        sources = [{"id": 1, "title": "Only source", "content": "text"}]
        scores, reordered = rerank_with_scores("query", sources)
        assert scores == [1.0]
        assert reordered == sources

    def test_empty_sources_returns_empty(self):
        """Empty input returns empty scores and sources."""
        from mcp_webgate.utils.reranker import rerank_with_scores

        scores, reordered = rerank_with_scores("query", [])
        assert scores == []
        assert reordered == []

    def test_list_query_is_joined(self):
        """A list query is joined into a single string for scoring."""
        from mcp_webgate.utils.reranker import rerank_with_scores

        sources = [
            {"id": 1, "title": "async Python", "content": "asyncio coroutines"},
            {"id": 2, "title": "Bread recipe", "content": "flour and yeast"},
        ]
        scores, reordered = rerank_with_scores(["python", "async"], sources)
        assert reordered[0]["id"] == 1
