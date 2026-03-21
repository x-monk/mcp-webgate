"""Configuration system: env vars > xsearch.toml > defaults."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel


class ServerConfig(BaseModel):
    max_download_mb: float = 1.0
    max_result_length: int = 4000
    search_timeout: float = 8.0
    oversampling_factor: int = 2
    auto_recovery_fetch: bool = False
    max_total_results: int = 20

    @property
    def max_download_bytes(self) -> int:
        return int(self.max_download_mb * 1024 * 1024)


class SearxngConfig(BaseModel):
    url: str = "http://localhost:8080"


class BraveConfig(BaseModel):
    api_key: str = ""
    safesearch: int = 1


class TavilyConfig(BaseModel):
    api_key: str = ""
    search_depth: str = "basic"


class BackendsConfig(BaseModel):
    default: str = "searxng"
    searxng: SearxngConfig = SearxngConfig()
    brave: BraveConfig = BraveConfig()
    tavily: TavilyConfig = TavilyConfig()


class Config(BaseModel):
    server: ServerConfig = ServerConfig()
    backends: BackendsConfig = BackendsConfig()


def _find_config_file() -> Path | None:
    """Look for xsearch.toml in CWD, then home directory."""
    candidates = [
        Path.cwd() / "xsearch.toml",
        Path.home() / "xsearch.toml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _apply_env(cfg: Config) -> None:
    """Override config values from XSEARCH_* env vars."""
    env_map = {
        "XSEARCH_DEFAULT_BACKEND": lambda v: setattr(cfg.backends, "default", v),
        "XSEARCH_SEARXNG_URL": lambda v: setattr(cfg.backends.searxng, "url", v),
        "XSEARCH_BRAVE_API_KEY": lambda v: setattr(cfg.backends.brave, "api_key", v),
        "XSEARCH_TAVILY_API_KEY": lambda v: setattr(cfg.backends.tavily, "api_key", v),
        "XSEARCH_MAX_DOWNLOAD_MB": lambda v: setattr(cfg.server, "max_download_mb", float(v)),
        "XSEARCH_MAX_RESULT_LENGTH": lambda v: setattr(cfg.server, "max_result_length", int(v)),
        "XSEARCH_SEARCH_TIMEOUT": lambda v: setattr(cfg.server, "search_timeout", float(v)),
        "XSEARCH_OVERSAMPLING_FACTOR": lambda v: setattr(cfg.server, "oversampling_factor", int(v)),
        "XSEARCH_AUTO_RECOVERY_FETCH": lambda v: setattr(cfg.server, "auto_recovery_fetch", v.lower() in ("1", "true", "yes")),
        "XSEARCH_MAX_TOTAL_RESULTS": lambda v: setattr(cfg.server, "max_total_results", int(v)),
    }
    for key, setter in env_map.items():
        val = os.environ.get(key)
        if val is not None:
            setter(val)


def load_config() -> Config:
    """Load config from toml file (if found) then apply env overrides."""
    toml_path = _find_config_file()
    if toml_path:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        cfg = Config.model_validate(data)
    else:
        cfg = Config()
    _apply_env(cfg)
    return cfg
