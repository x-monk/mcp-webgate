"""Results summarization: given sources + query, produce a concise Markdown answer."""

from __future__ import annotations

from .client import LLMClient


async def summarize_results(
    query: str | list[str],
    sources: list[dict],
    client: LLMClient,
    *,
    max_words: int = 500,
) -> str:
    """Summarize search results into a concise Markdown answer with inline citations.

    Sources have already been cleaned and truncated by the query pipeline
    (bounded by max_result_length / max_query_budget), so no additional
    input truncation is needed here.

    Raises on any LLM error — the caller is responsible for handling failures.

    Args:
        query: Original query string(s).
        sources: List of source dicts with keys: id, title, url, content.
        client: Configured LLMClient instance.
        max_words: Target word count for the generated summary (prompt guideline).
    """
    query_str = query if isinstance(query, str) else " | ".join(query)

    # Build context from all sources — already budget-bounded by the caller
    parts: list[str] = []
    for s in sources:
        parts.append(
            f"[{s['id']}] {s.get('title', '')}\n{s.get('url', '')}\n{s.get('content', '')}\n"
        )

    context = "\n".join(parts)

    prompt = (
        f"You are a research assistant. Based on the following search results for the query "
        f'"{query_str}", write a detailed report in Markdown (aim for at most {max_words} '
        f"words). Cite sources using their bracketed IDs like [1], [2], etc. "
        f"Do not add commentary about the sources themselves, and only include information contained in the provided search results.\n\n"
        f"Search results:\n{context}"
    )

    return await client.chat([{"role": "user", "content": prompt}])
