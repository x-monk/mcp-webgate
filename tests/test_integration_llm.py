"""Integration tests for Phase 4 LLM features against a real Ollama instance.

Requires a running Ollama server with the configured model available.
Tests are auto-skipped if WEBGATE_LLM_ENABLED is not set or Ollama is unreachable.

Run manually:
    WEBGATE_LLM_ENABLED=true uv run pytest tests/test_integration_llm.py -v
"""

from __future__ import annotations

import os

import httpx
import pytest

from mcp_webgate.config import LLMConfig
from mcp_webgate.llm.client import LLMClient
from mcp_webgate.llm.expander import expand_queries
from mcp_webgate.llm.summarizer import summarize_results
from mcp_webgate.utils.reranker import rerank_llm

# ---------------------------------------------------------------------------
# Skip condition
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "gemma3:27b"


def _ollama_available() -> bool:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


skip_if_unavailable = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama not reachable at localhost:11434 — skipping live LLM tests",
)


@pytest.fixture
def llm_cfg() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        base_url=OLLAMA_BASE_URL,
        api_key="",
        model=OLLAMA_MODEL,
        timeout=60.0,
    )


@pytest.fixture
def client(llm_cfg: LLMConfig) -> LLMClient:
    return LLMClient(llm_cfg)


# ---------------------------------------------------------------------------
# LLMClient — raw chat
# ---------------------------------------------------------------------------

@skip_if_unavailable
class TestLLMClientLive:
    @pytest.mark.asyncio
    async def test_chat_returns_string(self, client: LLMClient) -> None:
        """Live chat call returns a non-empty string."""
        result = await client.chat([{"role": "user", "content": "Reply with just the word: pong"}])
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.asyncio
    async def test_chat_follows_instruction(self, client: LLMClient) -> None:
        """Model follows a simple instruction."""
        result = await client.chat([
            {"role": "user", "content": 'Reply with only a JSON array: ["a", "b", "c"]. No other text.'}
        ])
        import json
        import re
        text = re.sub(r"^```[^\n]*\n?|\n?```$", "", result.strip())
        parsed = json.loads(text)
        assert isinstance(parsed, list)
        assert len(parsed) == 3


# ---------------------------------------------------------------------------
# Expander
# ---------------------------------------------------------------------------

@skip_if_unavailable
class TestExpandQueriesLive:
    @pytest.mark.asyncio
    async def test_returns_multiple_queries(self, client: LLMClient) -> None:
        """expand_queries returns a list starting with the original query."""
        result = await expand_queries("python asyncio tutorial", 3, client)
        assert isinstance(result, list)
        assert result[0] == "python asyncio tutorial"
        assert len(result) >= 2, f"Expected at least 2 queries, got: {result}"

    @pytest.mark.asyncio
    async def test_variants_are_different(self, client: LLMClient) -> None:
        """Generated variants differ from the original query."""
        result = await expand_queries("machine learning basics", 3, client)
        assert len(set(result)) > 1, "All queries are identical — expansion failed"

    @pytest.mark.asyncio
    async def test_respects_n_cap(self, client: LLMClient) -> None:
        """Number of returned queries does not exceed n."""
        result = await expand_queries("web scraping python", 3, client)
        assert len(result) <= 3


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------

@skip_if_unavailable
class TestSummarizeResultsLive:
    @pytest.fixture
    def sample_sources(self) -> list[dict]:
        return [
            {
                "id": 1,
                "title": "Python asyncio — official docs",
                "url": "https://docs.python.org/3/library/asyncio.html",
                "snippet": "asyncio is a library to write concurrent code using async/await syntax.",
                "content": (
                    "asyncio is a library to write concurrent code using the async/await syntax. "
                    "asyncio is used as a foundation for multiple Python asynchronous frameworks "
                    "that provide high-performance network and web servers, database connection "
                    "libraries, distributed task queues, etc. asyncio is often a perfect fit for "
                    "IO-bound and high-level structured network code."
                ),
                "truncated": False,
            },
            {
                "id": 2,
                "title": "Real Python: Async IO in Python",
                "url": "https://realpython.com/async-io-python/",
                "snippet": "Async IO is a concurrent programming design that has received dedicated support in Python.",
                "content": (
                    "Async IO is a concurrent programming design that has received dedicated "
                    "support in Python, evolving rapidly from Python 3.4 through 3.7+. "
                    "The asyncio package is billed by the Python docs as a library to write "
                    "concurrent code. The event loop is arguably the central execution device "
                    "of asyncio: it runs async tasks and callbacks, performs network IO operations, "
                    "and runs subprocesses."
                ),
                "truncated": False,
            },
        ]

    @pytest.mark.asyncio
    async def test_returns_non_empty_summary(
        self, client: LLMClient, sample_sources: list[dict]
    ) -> None:
        """summarize_results returns a non-empty string."""
        result = await summarize_results("python asyncio tutorial", sample_sources, client)
        assert isinstance(result, str)
        assert len(result.strip()) > 50, f"Summary too short: {result!r}"

    @pytest.mark.asyncio
    async def test_summary_contains_citation(
        self, client: LLMClient, sample_sources: list[dict]
    ) -> None:
        """Summary contains at least one bracketed citation [N]."""
        import re
        result = await summarize_results("python asyncio", sample_sources, client)
        citations = re.findall(r"\[\d+\]", result)
        assert len(citations) > 0, f"No citations found in summary: {result!r}"

    @pytest.mark.asyncio
    async def test_summary_is_about_the_query(
        self, client: LLMClient, sample_sources: list[dict]
    ) -> None:
        """Summary is topically relevant to the query."""
        result = await summarize_results("python asyncio", sample_sources, client)
        result_lower = result.lower()
        assert any(kw in result_lower for kw in ["async", "python", "concurrent", "await"]), (
            f"Summary does not mention expected keywords: {result!r}"
        )


# ---------------------------------------------------------------------------
# LLM Reranker
# ---------------------------------------------------------------------------

@skip_if_unavailable
class TestRerankLLMLive:
    @pytest.fixture
    def mixed_sources(self) -> list[dict]:
        return [
            {
                "id": 1,
                "title": "Best pasta recipes",
                "url": "https://cooking.com/pasta",
                "snippet": "Delicious Italian pasta recipes for every occasion.",
                "content": "pasta carbonara spaghetti bolognese italian cooking recipes",
                "truncated": False,
            },
            {
                "id": 2,
                "title": "Python asyncio event loop explained",
                "url": "https://realpython.com/asyncio",
                "snippet": "Deep dive into asyncio event loop and coroutines.",
                "content": "asyncio event loop coroutines tasks python async await",
                "truncated": False,
            },
            {
                "id": 3,
                "title": "asyncio.gather() usage patterns",
                "url": "https://docs.python.org/asyncio-gather",
                "snippet": "How to run coroutines concurrently with asyncio.gather.",
                "content": "asyncio gather concurrent coroutines python",
                "truncated": False,
            },
        ]

    @pytest.mark.asyncio
    async def test_places_relevant_first(
        self, client: LLMClient, mixed_sources: list[dict]
    ) -> None:
        """LLM reranker places the most relevant source(s) before the cooking result."""
        result = await rerank_llm("python asyncio tutorial", mixed_sources, client)
        assert len(result) == 3
        # Cooking source (id=1) should NOT be first
        assert result[0]["id"] != 1, (
            f"Cooking result ranked first for 'python asyncio' query — reranker not working: "
            f"{[r['id'] for r in result]}"
        )

    @pytest.mark.asyncio
    async def test_all_sources_preserved(
        self, client: LLMClient, mixed_sources: list[dict]
    ) -> None:
        """All input sources are present in the reranked output."""
        result = await rerank_llm("python asyncio", mixed_sources, client)
        assert {s["id"] for s in result} == {1, 2, 3}
