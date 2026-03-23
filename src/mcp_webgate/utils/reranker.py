"""Two-tier result re-ranking.

Tier 1 (always active): deterministic BM25 keyword overlap — zero cost, no LLM.
Tier 2 (opt-in): LLM-assisted relevance scoring via a configured LLMClient.

Pipeline position in query: clean → rerank → top-N → summarizer → output.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.client import LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _bm25_scores(
    query_tokens: list[str],
    docs: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Return BM25 scores for each document against the query tokens."""
    N = len(docs)
    tokenized = [_tokenize(d) for d in docs]
    avg_len = sum(len(t) for t in tokenized) / max(N, 1)

    scores: list[float] = []
    for doc_tokens in tokenized:
        tf_map = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        score = 0.0
        for term in set(query_tokens):
            tf = tf_map.get(term, 0)
            df = sum(1 for t in tokenized if term in t)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            score += idf * numerator / max(denominator, 1e-9)
        scores.append(score)

    return scores


# ---------------------------------------------------------------------------
# Tier 1 — deterministic BM25
# ---------------------------------------------------------------------------

def rerank_deterministic(
    query: str | list[str],
    sources: list[dict],
) -> list[dict]:
    """Rerank sources by BM25 score against the query. Always active.

    Uses title + snippet + first 3000 chars of content as the document text
    for a strong signal from the actual page body while staying lightweight.

    Returns the reordered source list (original list is not mutated).
    """
    if len(sources) <= 1:
        return sources

    query_str = query if isinstance(query, str) else " ".join(query)
    query_tokens = _tokenize(query_str)

    docs = [
        f"{s.get('title', '')} {s.get('snippet', '')} {s.get('content', '')[:3000]}"
        for s in sources
    ]

    scores = _bm25_scores(query_tokens, docs)
    ranked = sorted(zip(scores, range(len(sources))), reverse=True)
    return [sources[i] for _, i in ranked]


def rerank_with_scores(
    query: str | list[str],
    sources: list[dict],
) -> tuple[list[float], list[dict]]:
    """Rerank sources by BM25 score and return (scores_in_new_order, reordered_sources).

    Unlike rerank_deterministic, this variant preserves the raw BM25 scores so
    callers can use them for proportional budget allocation (adaptive_budget).
    """
    if len(sources) <= 1:
        return ([1.0] * len(sources), list(sources))

    query_str = query if isinstance(query, str) else " ".join(query)
    query_tokens = _tokenize(query_str)

    docs = [
        f"{s.get('title', '')} {s.get('snippet', '')} {s.get('content', '')[:3000]}"
        for s in sources
    ]

    scores = _bm25_scores(query_tokens, docs)
    ranked = sorted(zip(scores, range(len(sources))), reverse=True)
    sorted_scores = [s for s, _ in ranked]
    sorted_sources = [sources[i] for _, i in ranked]
    return sorted_scores, sorted_sources


# ---------------------------------------------------------------------------
# Tier 2 — LLM-assisted (opt-in)
# ---------------------------------------------------------------------------

async def rerank_llm(
    query: str | list[str],
    sources: list[dict],
    client: LLMClient,
) -> list[dict]:
    """Rerank sources using an LLM relevance judgment.

    The LLM receives only title + snippet + first 200 chars of content per
    source (lightweight input) and returns a ranked list of source IDs.

    Falls back to the input order on any error.
    """
    if len(sources) <= 1:
        return sources

    query_str = query if isinstance(query, str) else " | ".join(query)

    items = "\n".join(
        f"[{s['id']}] {s.get('title', '')} — "
        f"{(s.get('snippet') or s.get('content', ''))[:200]}"
        for s in sources
    )

    prompt = (
        f'Rank the following search results by relevance to the query: "{query_str}"\n'
        "Output only a JSON array of IDs in order from most to least relevant. "
        "No explanation, no markdown.\n\n"
        f"Results:\n{items}"
    )

    try:
        text = await client.chat([{"role": "user", "content": prompt}])
        text = re.sub(r"^```[^\n]*\n?|\n?```$", "", text.strip())
        ranked_ids = json.loads(text)
        if isinstance(ranked_ids, list):
            id_to_source = {s["id"]: s for s in sources}
            reranked = [id_to_source[i] for i in ranked_ids if i in id_to_source]
            # Append any sources the LLM omitted
            mentioned = set(ranked_ids)
            reranked += [s for s in sources if s["id"] not in mentioned]
            return reranked
    except Exception:
        pass

    return sources
