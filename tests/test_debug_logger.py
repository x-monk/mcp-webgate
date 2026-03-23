"""Tests for the debug logging system."""

from __future__ import annotations

import pytest

from mcp_webgate.utils import logger as logger_module
from mcp_webgate.utils.logger import log_fetch, log_query, setup_debug_logging


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset _configured flag and _log_target between tests."""
    original_configured = logger_module._configured
    original_target = logger_module._log_target
    yield
    logger_module._configured = original_configured
    logger_module._log_target = original_target


class TestSetupDebugLogging:
    def test_setup_configures_to_stderr(self):
        logger_module._configured = False
        setup_debug_logging()
        assert logger_module._configured is True
        assert logger_module._log_target == "stderr"

    def test_setup_is_idempotent(self):
        logger_module._configured = False
        setup_debug_logging()
        assert logger_module._log_target == "stderr"
        # second call should not change target
        setup_debug_logging(log_file="/tmp/other.log")
        assert logger_module._log_target == "stderr"

    def test_setup_with_file(self, tmp_path):
        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        assert logger_module._configured is True
        assert logger_module._log_target == log_path
        # startup message should be written
        content = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "debug logging initialized" in content


class TestLogFetch:
    def test_log_fetch_emits_message(self, tmp_path):
        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        log_fetch(
            url="https://example.com",
            raw_bytes=10240,
            clean_chars=3000,
            elapsed_ms=250.0,
            success=True,
        )

        output = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "fetch" in output
        assert "example.com" in output
        assert "ok" in output

    def test_log_fetch_failed_status(self, tmp_path):
        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        log_fetch(url="https://example.com", raw_bytes=0, clean_chars=0, elapsed_ms=100, success=False)
        output = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "failed" in output


class TestLogQuery:
    def test_log_query_emits_message(self, tmp_path):
        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        log_query(
            queries=["python tutorial"],
            num_requested=5,
            fetched=4,
            failed=1,
            gap_filled=0,
            raw_bytes_total=2 * 1024 * 1024,
            clean_chars_total=12000,
            elapsed_ms=1800.0,
        )

        output = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "query" in output
        assert "python tutorial" in output
        assert "ok=4" in output
        assert "fail=1" in output

    def test_log_query_multiple_queries_abbreviated(self, tmp_path):
        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        log_query(
            queries=["q1", "q2", "q3"],
            num_requested=3,
            fetched=3,
            failed=0,
            gap_filled=0,
            raw_bytes_total=0,
            clean_chars_total=0,
            elapsed_ms=500,
        )

        output = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "q1 [+2]" in output


class TestConfigValidators:
    def test_invalid_max_download_mb(self):
        from pydantic import ValidationError
        from mcp_webgate.config import ServerConfig
        with pytest.raises(ValidationError, match="max_download_mb"):
            ServerConfig(max_download_mb=0)

    def test_invalid_max_result_length(self):
        from pydantic import ValidationError
        from mcp_webgate.config import ServerConfig
        with pytest.raises(ValidationError, match="max_result_length"):
            ServerConfig(max_result_length=-1)

    def test_invalid_oversampling_factor(self):
        from pydantic import ValidationError
        from mcp_webgate.config import ServerConfig
        with pytest.raises(ValidationError, match="oversampling_factor"):
            ServerConfig(oversampling_factor=0)

    def test_invalid_max_total_results(self):
        from pydantic import ValidationError
        from mcp_webgate.config import ServerConfig
        with pytest.raises(ValidationError, match="max_total_results"):
            ServerConfig(max_total_results=0)

    def test_valid_config_passes(self):
        from mcp_webgate.config import ServerConfig
        cfg = ServerConfig(max_download_mb=2.0, max_result_length=8000, oversampling_factor=3)
        assert cfg.max_download_mb == 2.0


class TestLogAdaptiveBudget:
    def test_emits_header_and_per_source_lines(self, tmp_path):
        """log_adaptive_budget emits one header line and one line per source."""
        from mcp_webgate.utils.logger import log_adaptive_budget, setup_debug_logging

        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        sources = [
            {"url": "https://example.com/a", "content": "x" * 100},
            {"url": "https://example.com/b", "content": "y" * 50},
        ]
        log_adaptive_budget(
            sources=sources,
            bm25_scores=[2.5, 1.0],
            initial_allocs=[200, 200],
            allocs=[250, 150],
            total_budget=400,
            fetch_limit=300,
        )

        output = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "adaptive_budget" in output
        assert "example.com/a" in output
        assert "example.com/b" in output

    def test_handles_zero_total_score(self, tmp_path):
        """log_adaptive_budget does not divide by zero when all BM25 scores are 0."""
        from mcp_webgate.utils.logger import log_adaptive_budget, setup_debug_logging

        logger_module._configured = False
        log_path = str(tmp_path / "test.log")
        setup_debug_logging(log_file=log_path)

        sources = [{"url": "https://x.com", "content": "text"}]
        log_adaptive_budget(
            sources=sources,
            bm25_scores=[0.0],
            initial_allocs=[100],
            allocs=[100],
            total_budget=100,
            fetch_limit=100,
        )
        assert "adaptive_budget" in (tmp_path / "test.log").read_text(encoding="utf-8")
