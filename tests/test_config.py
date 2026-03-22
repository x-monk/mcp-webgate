"""Tests for configuration system."""

import os

from mcp_webgate.config import Config, load_config


class TestConfig:
    def test_defaults(self):
        cfg = Config()
        assert cfg.server.max_download_mb == 1.0
        assert cfg.server.max_result_length == 8000
        assert cfg.server.search_timeout == 8.0
        assert cfg.backends.default == "searxng"

    def test_max_download_bytes(self):
        cfg = Config()
        assert cfg.server.max_download_bytes == 1048576  # 1MB


class TestLoadConfig:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WEBGATE_MAX_RESULT_LENGTH", "8000")
        monkeypatch.setenv("WEBGATE_DEFAULT_BACKEND", "brave")
        cfg = load_config()
        assert cfg.server.max_result_length == 8000
        assert cfg.backends.default == "brave"

    def test_env_bool_true(self, monkeypatch):
        monkeypatch.setenv("WEBGATE_AUTO_RECOVERY_FETCH", "true")
        cfg = load_config()
        assert cfg.server.auto_recovery_fetch is True

    def test_env_bool_false(self, monkeypatch):
        monkeypatch.setenv("WEBGATE_AUTO_RECOVERY_FETCH", "false")
        cfg = load_config()
        assert cfg.server.auto_recovery_fetch is False
