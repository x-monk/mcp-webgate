"""Debug logger for mcp-webgate.

When debug mode is enabled, every tool invocation emits a structured log entry
with query info, byte counts, timing, and failure stats.

Output target:
- If log_file is set: appends to that file.
- Otherwise: writes to stderr.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_log_target: str = ""  # "stderr" or resolved file path
_configured = False


def setup_debug_logging(log_file: str = "") -> None:
    """Configure the webgate logger. Called once at server startup when debug=True."""
    global _configured, _log_target
    if _configured:
        return

    if log_file:
        _log_target = str(Path(os.path.expandvars(log_file)).expanduser())
    else:
        _log_target = "stderr"

    _configured = True
    _emit("debug logging initialized (target=%s)", _log_target)


def _emit(fmt: str, *args: object) -> None:
    """Write a formatted log line to the configured target."""
    if not _configured:
        return
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    msg = fmt % args if args else fmt
    line = f"{ts} [webgate] DEBUG {msg}\n"

    if _log_target == "stderr":
        sys.stderr.write(line)
        sys.stderr.flush()
    else:
        with open(_log_target, "a", encoding="utf-8") as f:
            f.write(line)


def log_fetch(
    *,
    url: str,
    raw_bytes: int,
    clean_chars: int,
    elapsed_ms: float,
    success: bool,
) -> None:
    """Log a single fetch tool invocation."""
    status = "ok" if success else "failed"
    raw_kb = raw_bytes / 1024
    clean_kb = clean_chars / 1024
    _emit(
        "fetch | %s | status=%s raw=%.1fKB clean=%.1fKB elapsed=%.0fms",
        url,
        status,
        raw_kb,
        clean_kb,
        elapsed_ms,
    )


def _short_url(url: str, max_len: int = 58) -> str:
    """Shorten a URL to hostname+path, truncated to max_len chars."""
    try:
        p = urlparse(url)
        short = p.netloc + p.path
    except Exception:
        short = url
    return (short[: max_len - 1] + "…") if len(short) > max_len else short


def _emit_fetch_row(url: str, url_ms: float, raw_bytes: int, clean_chars: int, ok: bool, indent: str) -> None:
    """Emit one fetch detail row with consistent column alignment."""
    status = "ok  " if ok else "fail"
    raw_kb = raw_bytes / 1024
    clean_kb = clean_chars / 1024
    short = _short_url(url)
    # data_str is always 18 chars so the ms column aligns on both ok and fail rows:
    # ok:   "%6.1fKB → %5.1fKB" = 6+2+3+5+2 = 18 chars
    # fail: "%-18s" % "failed"  = 18 chars
    if ok:
        data_str = f"{raw_kb:6.1f}KB → {clean_kb:5.1f}KB"
    else:
        data_str = f"{'failed':<18}"
    _emit("%s[%s]  %-60s  %s  %5.0fms", indent, status, short, data_str, url_ms)


def log_adaptive_budget(
    *,
    sources: list[dict],
    bm25_scores: list[float],
    initial_allocs: list[int],
    allocs: list[int],
    total_budget: int,
    fetch_limit: int,
) -> None:
    """Log per-source adaptive budget allocation after BM25 scoring.

    sources, bm25_scores, initial_allocs, allocs must be parallel lists
    (same order post-rerank).  initial_allocs are pre-redistribution,
    allocs are post-redistribution.
    """
    total_score = sum(bm25_scores)
    redistributed = sum(allocs) - sum(initial_allocs)
    # redistributed can be ~0 when no surplus existed
    _emit(
        "  adaptive_budget | total_budget=%d  fetch_limit=%d  sources=%d  Σbm25=%.2f",
        total_budget,
        fetch_limit,
        len(sources),
        total_score,
    )
    for source, score, init, final_alloc in zip(sources, bm25_scores, initial_allocs, allocs):
        pct = (score / total_score * 100) if total_score > 0 else 0.0
        final = len(source["content"])
        short = _short_url(source.get("url", ""), max_len=46)
        delta = final_alloc - init
        delta_str = f"+{delta:5d}" if delta > 0 else f"{delta:6d}" if delta < 0 else "     0"
        _emit(
            "    [%5.2f | %4.1f%%]  init=%5d  Δ=%s  alloc=%5d  final=%5d  %s",
            score,
            pct,
            init,
            delta_str,
            final_alloc,
            final,
            short,
        )


def log_query(
    *,
    queries: list[str],
    num_requested: int,
    fetched: int,
    failed: int,
    gap_filled: int,
    raw_bytes_total: int,
    clean_chars_total: int,
    elapsed_ms: float,
    expansion_ms: float = 0.0,
    search_ms: float = 0.0,
    fetch_ms: float = 0.0,
    fetch_details: list[tuple[str, float, int, int, bool, int]] | None = None,
    summary_chars: int = 0,
) -> None:
    """Log a full query tool invocation with optional per-URL breakdown.

    fetch_details entries: (url, elapsed_ms, raw_bytes, clean_chars, success, query_idx)
    When multiple queries are present, results are grouped under their originating query.
    """
    q_display = queries[0] if len(queries) == 1 else f"{queries[0]} [+{len(queries) - 1}]"
    counts = f"ok={fetched} fail={failed}"
    if gap_filled:
        counts += f" gap={gap_filled}"
    timing_parts = []
    if expansion_ms >= 100:  # only show expand when it actually ran (>= 100 ms)
        timing_parts.append(f"expand={expansion_ms / 1000:.1f}s")
    timing_parts += [
        f"search={search_ms / 1000:.1f}s",
        f"fetch={fetch_ms / 1000:.1f}s",
        f"total={elapsed_ms / 1000:.1f}s",
    ]
    timing = " ".join(timing_parts)
    _emit("query | %r | %s | %s", q_display, timing, counts)

    if fetch_details:
        multi = len(queries) > 1
        if multi:
            # Group rows by originating query
            from collections import defaultdict
            by_query: dict[int, list] = defaultdict(list)
            for detail in fetch_details:
                by_query[detail[5]].append(detail)
            for qi in sorted(by_query.keys()):
                q_label = queries[qi] if qi < len(queries) else f"Q{qi + 1}"
                _emit("  [Q%d]  %s", qi + 1, q_label)
                for url, url_ms, raw_bytes, clean_chars, ok, _ in by_query[qi]:
                    _emit_fetch_row(url, url_ms, raw_bytes, clean_chars, ok, indent="       ")
        else:
            for url, url_ms, raw_bytes, clean_chars, ok, _ in fetch_details:
                _emit_fetch_row(url, url_ms, raw_bytes, clean_chars, ok, indent="  ")

    raw_mb = raw_bytes_total / (1024 * 1024)
    clean_kb = clean_chars_total / 1024
    output_kb = summary_chars / 1024 if summary_chars else clean_kb
    output_label = "summary" if summary_chars else "output"
    _emit("  >>>  raw=%.2fMB  clean=%.1fKB  %s=%.1fKB", raw_mb, clean_kb, output_label, output_kb)
