"""Query expansion: given one query, generate N complementary queries via LLM."""

from __future__ import annotations

import json
import re

from .client import LLMClient


async def expand_queries(query: str, n: int, client: LLMClient) -> list[str]:
    """Generate up to n-1 complementary queries and prepend the original.

    Returns [query] on any error — the pipeline always has at least one query.

    Args:
        query: The original search query.
        n: Target total number of queries (original + generated).
        client: Configured LLMClient instance.
    """
    if n <= 1:
        return [query]

    prompt = (
        f"Generate up to {n - 1} complementary search queries for the following topic. "
        "Each query should approach the topic from a different angle or add specificity. "
        "Output only a JSON array of strings, no explanation, no markdown.\n\n"
        f"Query: {query}"
    )

    try:
        text = await client.chat([{"role": "user", "content": prompt}])
        # Strip markdown fences if present
        text = re.sub(r"^```[^\n]*\n?|\n?```$", "", text.strip())
        expanded = json.loads(text)
        if isinstance(expanded, list) and expanded:
            variants = [str(q) for q in expanded][: n - 1]
            return [query] + variants
    except Exception:
        pass

    return [query]
