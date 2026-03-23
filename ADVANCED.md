# Advanced & Experimental Features

This document covers internal ranking mechanics and opt-in experimental features not documented in the main README.

## 🏆 Ranking Pipeline

The query pipeline applies two independent reranking tiers after fetching and cleaning all pages. Tier 1 is always active; Tier 2 is opt-in.

### Tier 1 — Deterministic BM25 (`rerank_deterministic`)

BM25 (Best Match 25) is a probabilistic keyword-overlap scoring function widely used in information retrieval. It measures how relevant a document is to a query based on how often the query terms appear in the document, how rare those terms are across the whole collection, and how long the document is. It does not understand semantics — a page about "async Python" will not match a query about "concurrent programming" unless those exact words appear.

For each fetched page, it computes a relevance score against the combined query text using term frequency (TF), inverse document frequency (IDF), and document length normalization.

**Document representation:** title + snippet + first 3000 chars of cleaned content. The window is large enough to capture the main body of most articles while still avoiding footer/boilerplate noise. When adaptive budget is active, pages are pre-cleaned with a generous `fetch_limit` before BM25 runs, so this window is filled with actual body text rather than just the search-engine snippet.

**Tuning parameters (hardcoded, pre-tuned for web search):**
- `k1 = 1.5` — TF saturation. A term appearing 10× in a page is not 10× more relevant than one appearing 2×; score growth diminishes as frequency increases.
- `b = 0.75` — Length normalization weight. Long pages are penalized to avoid score inflation from sheer verbosity; short, keyword-dense pages score relatively higher.

**Properties:**
- Zero cost: no network calls, no LLM, pure Python math.
- Fully deterministic: same input always produces the same order.
- Operates on keyword overlap, not semantics. A highly relevant page using synonyms may score lower than expected.

**Position in pipeline:** after cleaning, before LLM rerank and summarization.

---

### Tier 2 — LLM-assisted reranking (`rerank_llm`)

When `llm.llm_rerank_enabled = true`, a second reranking pass is performed using an LLM.

The LLM receives a lightweight representation of each source (title + snippet + first 200 chars) and is asked to return a JSON array of source IDs ordered from most to least relevant. The result is an **ordered list only** — no numeric scores are returned.

**Why no scores from the LLM?**
LLMs asked to produce numeric relevance scores tend to cluster results (e.g., everything scores 7-9/10) and are inconsistent across calls. An ordered ranking is both simpler to prompt for and more reliable to parse.

**Fallback:** any error (timeout, malformed JSON, missing IDs) silently falls back to the Tier 1 order — Tier 2 never degrades output quality, it only improves ordering when it succeeds.

**Cost:** one additional LLM call per query, adding latency proportional to the number of sources and the model's speed.

**Interaction with adaptive budget:** when adaptive budget is active, the char allocation for each source is computed from BM25 scores *before* LLM reranking. The LLM rerank changes the *order* in which sources are presented to the summarizer, but does not alter how many chars each source received.

---

## [EXPERIMENTAL] Adaptive Budget Allocation

**Config:** `server.adaptive_budget = true` (default: `false`)
**Env var:** `WEBGATE_ADAPTIVE_BUDGET=1`
**CLI:** `--adaptive-budget`

### The problem it solves

In the standard pipeline, the per-page char limit is computed as a flat value:

```
per_page_limit = max_query_budget // num_candidates
```

All sources receive the same char ceiling regardless of relevance. A comprehensive tutorial and a thin blog post with one sentence both get, say, 2.400 chars. The tutorial is arbitrarily truncated; the thin post wastes its allocation.

### How it works

The adaptive budget replaces the flat allocation with a three-phase approach:

**Phase 1 — Generous fetch**

All pages are cleaned with a relaxed per-page limit:

```
fetch_limit = max_result_length × adaptive_budget_fetch_factor
```

Default: `8000 × 3 = 24.000 chars per page`. This gives the reranker enough signal to judge quality without permanently allocating the full budget to every source.

**Phase 2 — BM25 scoring**

`rerank_with_scores()` runs BM25 and returns both the ranked order *and* the raw scores. Unlike `rerank_deterministic`, which discards scores after sorting, this variant preserves them for the allocation step.

**Phase 3 — Proportional redistribution**

Each source receives a char allocation proportional to its BM25 score:

```
alloc_i = max(200, min(fetch_limit, int(score_i / Σscores × total_budget)))
```

- `total_budget` = `max_query_budget` (or `max_query_budget × llm.input_budget_factor` when summarization is active)
- Floor of 200 chars ensures even low-scoring sources retain their snippet
- Ceiling of `fetch_limit` prevents a single dominant source from consuming the entire budget
- If all BM25 scores are zero (pathological case), falls back to flat distribution

**Phase 4 — Surplus redistribution**

After Phase 3, some sources may have less actual content than their allocation (failed fetches, thin pages, paywalled content). Keeping that unused budget locked to them wastes the total budget.

A redistribution loop (max 5 iterations, converges in 1-2) reclaims the surplus and gives it back to "hungry" sources (those whose content exceeds their current alloc):

```
for each source:
    if actual_content < alloc_i:
        surplus += alloc_i - actual_content
        alloc_i = actual_content          # shrink to actual
    elif actual_content > alloc_i:
        mark as hungry

distribute surplus proportionally to bm25_score_i of hungry sources
repeat until surplus == 0 or no hungry sources remain
```

This is a pure in-memory operation — no re-fetch. Failed sources end up with their snippet (≈ 50–200 chars); the recovered budget flows to the highest-scoring pages that were still truncated.

Sources are then re-truncated in-place (`content[:alloc_i]`) — no re-fetch needed.

### Debug visibility (`trace` mode)

When `server.trace = true` (env: `WEBGATE_TRACE=1`, CLI: `--trace`), the server logs a per-source breakdown after each adaptive budget cycle:

```
adaptive_budget | total_budget=96000  fetch_limit=24000  sources=20  Σbm25=61.29
  [ 8.18 | 13.3%]  init=12810  Δ=+ 2930  alloc=15740  final=15740  digitalocean.com/...
  [ 3.84 |  6.3%]  init= 6018  Δ= -5968  alloc=   50  final=   50  reddit.com/...
```

**Column legend:**

| Column | Meaning |
|--------|---------|
| `[8.18 \| 13.3%]` | BM25 score for this source and its percentage of the total score across all sources |
| `init=12810` | Initial char allocation from Phase 3 (proportional to BM25 score) |
| `Δ=+2930` | Budget change from surplus redistribution — positive means the source absorbed surplus from thinner pages |
| `Δ=-5968` | Negative delta means this source donated surplus (its actual content was shorter than its allocation) |
| `alloc=15740` | Final char allocation after redistribution |
| `final=15740` | Actual content length after truncation to the final allocation |

A source with `Δ < 0` was a thin page (failed fetch, paywalled, or just short). A source with a large `Δ > 0` was the main beneficiary — a long, keyword-dense page that was still truncated and absorbed the recovered budget.

A large negative Δ indicates a source that donated surplus (failed fetch or thin page). A large positive Δ indicates a hungry source that absorbed the recovered budget.

### Worked example

Continuing the DigitalOcean tutorial case from the README:

| Source | BM25 score | % of total | Allocation (32k budget) |
|---|---|---|---|
| digitalocean.com tutorial | 4.7 | 38% | ~12.160 chars |
| modelcontextprotocol.io docs | 3.1 | 25% | ~8.000 chars |
| anthropic.com news | 2.0 | 16% | ~5.120 chars |
| ... 10 other sources | 2.6 combined | 21% | ~6.720 total |

Compared to flat allocation (2.460 chars each), the tutorial receives 5× more content. The BM25 signal correctly identifies it as the most keyword-dense match for the query.

### Config reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `server.adaptive_budget` | bool | `false` | Enable adaptive budget allocation |
| `server.adaptive_budget_fetch_factor` | int | `3` | Generous pre-rank fetch multiplier |

**Env vars:** `WEBGATE_ADAPTIVE_BUDGET`, `WEBGATE_ADAPTIVE_BUDGET_FETCH_FACTOR`
**CLI args:** `--adaptive-budget` / `--no-adaptive-budget`, `--adaptive-budget-fetch-factor N`

### Known limitations

- BM25 is keyword-based. Semantically relevant sources that use different terminology will be under-allocated.
- The fetch_factor multiplier increases bandwidth consumption (up to 3× raw HTML downloaded per page).
- With very skewed score distributions, the floor/ceiling clamps may cause the total allocated chars to exceed `max_query_budget` slightly. This is acceptable — the over-run is bounded by `n_sources × 200` worst case.
- Interaction with LLM summarization: the summarizer receives sources with variable-length content. This is intentional — the LLM should naturally weight denser sources more heavily.
