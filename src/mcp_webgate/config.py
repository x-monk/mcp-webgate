"""Configuration system: CLI args > env vars > webgate.toml > defaults."""

from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, field_validator


class ServerConfig(BaseModel):
    max_download_mb: int = 1
    max_result_length: int = 8000
    search_timeout: int = 8
    oversampling_factor: int = 2
    auto_recovery_fetch: bool = False
    max_total_results: int = 20
    max_query_budget: int = 32000
    max_search_queries: int = 5
    results_per_query: int = 5
    blocked_domains: list[str] = []
    allowed_domains: list[str] = []
    debug: bool = False
    log_file: str = ""  # empty = stderr when debug is enabled
    trace: bool = False  # include full sources in summarized response; also enables reranking stats logging
    # EXPERIMENTAL: proportional char allocation based on BM25 rank score
    adaptive_budget: bool = False
    adaptive_budget_fetch_factor: int = 3  # generous pre-rank fetch multiplier

    @field_validator("max_download_mb")
    @classmethod
    def _validate_download_mb(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_download_mb must be > 0")
        return v

    @field_validator("max_result_length")
    @classmethod
    def _validate_result_length(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_result_length must be > 0")
        return v

    @field_validator("oversampling_factor")
    @classmethod
    def _validate_oversampling(cls, v: int) -> int:
        if v < 1:
            raise ValueError("oversampling_factor must be >= 1")
        return v

    @field_validator("max_total_results")
    @classmethod
    def _validate_max_results(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_total_results must be >= 1")
        return v

    @field_validator("max_query_budget")
    @classmethod
    def _validate_query_budget(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_query_budget must be >= 1")
        return v

    @field_validator("max_search_queries")
    @classmethod
    def _validate_max_search_queries(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_search_queries must be >= 1")
        return v

    @field_validator("results_per_query")
    @classmethod
    def _validate_results_per_query(cls, v: int) -> int:
        if v < 1:
            raise ValueError("results_per_query must be >= 1")
        return v

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


class ExaConfig(BaseModel):
    api_key: str = ""
    num_sentences: int = 3
    type: str = "neural"  # "neural" or "keyword"


class SerpapiConfig(BaseModel):
    api_key: str = ""
    engine: str = "google"
    gl: str = "us"
    hl: str = "en"
    safe: str = "off"


class LLMConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "llama3.2"
    timeout: int = 30
    expansion_enabled: bool = True
    summarization_enabled: bool = True
    llm_rerank_enabled: bool = (
        False  # opt-in: adds latency; deterministic BM25 always runs
    )
    max_summary_words: int = (
        0  # 0 = derived from max_query_budget / 5; set explicitly to override
    )
    input_budget_factor: int = 3  # total LLM input budget = max_query_budget × factor


class BackendsConfig(BaseModel):
    default: str = "searxng"
    searxng: SearxngConfig = SearxngConfig()
    brave: BraveConfig = BraveConfig()
    tavily: TavilyConfig = TavilyConfig()
    exa: ExaConfig = ExaConfig()
    serpapi: SerpapiConfig = SerpapiConfig()


class Config(BaseModel):
    server: ServerConfig = ServerConfig()
    backends: BackendsConfig = BackendsConfig()
    llm: LLMConfig = LLMConfig()


def _find_config_file() -> Path | None:
    """Look for webgate.toml in CWD, then home directory."""
    candidates = [
        Path.cwd() / "webgate.toml",
        Path.home() / "webgate.toml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _apply_env(cfg: Config) -> None:
    """Override config values from WEBGATE_* env vars."""
    env_map = {
        "WEBGATE_DEFAULT_BACKEND": lambda v: setattr(cfg.backends, "default", v),
        "WEBGATE_SEARXNG_URL": lambda v: setattr(cfg.backends.searxng, "url", v),
        "WEBGATE_BRAVE_API_KEY": lambda v: setattr(cfg.backends.brave, "api_key", v),
        "WEBGATE_TAVILY_API_KEY": lambda v: setattr(cfg.backends.tavily, "api_key", v),
        "WEBGATE_EXA_API_KEY": lambda v: setattr(cfg.backends.exa, "api_key", v),
        "WEBGATE_SERPAPI_API_KEY": lambda v: setattr(
            cfg.backends.serpapi, "api_key", v
        ),
        "WEBGATE_SERPAPI_ENGINE": lambda v: setattr(cfg.backends.serpapi, "engine", v),
        "WEBGATE_SERPAPI_GL": lambda v: setattr(cfg.backends.serpapi, "gl", v),
        "WEBGATE_SERPAPI_HL": lambda v: setattr(cfg.backends.serpapi, "hl", v),
        "WEBGATE_MAX_DOWNLOAD_MB": lambda v: setattr(
            cfg.server, "max_download_mb", int(v)
        ),
        "WEBGATE_MAX_RESULT_LENGTH": lambda v: setattr(
            cfg.server, "max_result_length", int(v)
        ),
        "WEBGATE_SEARCH_TIMEOUT": lambda v: setattr(
            cfg.server, "search_timeout", int(v)
        ),
        "WEBGATE_OVERSAMPLING_FACTOR": lambda v: setattr(
            cfg.server, "oversampling_factor", int(v)
        ),
        "WEBGATE_AUTO_RECOVERY_FETCH": lambda v: setattr(
            cfg.server, "auto_recovery_fetch", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_MAX_TOTAL_RESULTS": lambda v: setattr(
            cfg.server, "max_total_results", int(v)
        ),
        "WEBGATE_MAX_QUERY_BUDGET": lambda v: setattr(
            cfg.server, "max_query_budget", int(v)
        ),
        "WEBGATE_MAX_SEARCH_QUERIES": lambda v: setattr(
            cfg.server, "max_search_queries", int(v)
        ),
        "WEBGATE_RESULTS_PER_QUERY": lambda v: setattr(
            cfg.server, "results_per_query", int(v)
        ),
        "WEBGATE_DEBUG": lambda v: setattr(
            cfg.server, "debug", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LOG_FILE": lambda v: setattr(cfg.server, "log_file", v),
        "WEBGATE_TRACE": lambda v: setattr(
            cfg.server, "trace", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LLM_ENABLED": lambda v: setattr(
            cfg.llm, "enabled", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LLM_BASE_URL": lambda v: setattr(cfg.llm, "base_url", v),
        "WEBGATE_LLM_API_KEY": lambda v: setattr(cfg.llm, "api_key", v),
        "WEBGATE_LLM_MODEL": lambda v: setattr(cfg.llm, "model", v),
        "WEBGATE_LLM_TIMEOUT": lambda v: setattr(cfg.llm, "timeout", int(v)),
        "WEBGATE_LLM_EXPANSION_ENABLED": lambda v: setattr(
            cfg.llm, "expansion_enabled", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LLM_SUMMARIZATION_ENABLED": lambda v: setattr(
            cfg.llm, "summarization_enabled", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LLM_RERANK_ENABLED": lambda v: setattr(
            cfg.llm, "llm_rerank_enabled", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_LLM_MAX_SUMMARY_WORDS": lambda v: setattr(
            cfg.llm, "max_summary_words", int(v)
        ),
        "WEBGATE_LLM_INPUT_BUDGET_FACTOR": lambda v: setattr(
            cfg.llm, "input_budget_factor", int(v)
        ),
        "WEBGATE_ADAPTIVE_BUDGET": lambda v: setattr(
            cfg.server, "adaptive_budget", v.lower() in ("1", "true", "yes")
        ),
        "WEBGATE_ADAPTIVE_BUDGET_FETCH_FACTOR": lambda v: setattr(
            cfg.server, "adaptive_budget_fetch_factor", int(v)
        ),
    }
    for key, setter in env_map.items():
        val = os.environ.get(key)
        if val is not None:
            setter(val)


def parse_cli_args() -> argparse.Namespace:
    """Parse command-line arguments. All are optional; None means 'not provided'."""
    p = argparse.ArgumentParser(
        prog="mcp-webgate",
        description="Denoised web search MCP server",
        add_help=True,
    )
    # --- server ---
    p.add_argument("--default-backend", default=None, metavar="NAME",
                   help="Search backend to use (searxng|brave|tavily|exa|serpapi)")
    p.add_argument("--max-download-mb", type=int, default=None, metavar="N",
                   help="Hard cap on per-page download size in MB")
    p.add_argument("--max-result-length", type=int, default=None, metavar="N",
                   help="Hard cap on chars per cleaned page")
    p.add_argument("--search-timeout", type=int, default=None, metavar="SEC",
                   help="HTTP timeout for search/fetch requests in seconds")
    p.add_argument("--oversampling-factor", type=int, default=None, metavar="N",
                   help="Multiplier for candidate results before reranking")
    p.add_argument("--auto-recovery-fetch", action=argparse.BooleanOptionalAction, default=None,
                   help="Enable gap-filler second fetch round")
    p.add_argument("--max-total-results", type=int, default=None, metavar="N",
                   help="Hard cap on total results per query call")
    p.add_argument("--max-query-budget", type=int, default=None, metavar="CHARS",
                   help="Total char budget across all sources")
    p.add_argument("--max-search-queries", type=int, default=None, metavar="N",
                   help="Maximum number of queries per call")
    p.add_argument("--results-per-query", type=int, default=None, metavar="N",
                   help="Default results fetched per query")
    p.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None,
                   help="Enable debug logging")
    p.add_argument("--log-file", default=None, metavar="PATH",
                   help="Log file path (empty = stderr when debug enabled)")
    p.add_argument("--trace", action=argparse.BooleanOptionalAction, default=None,
                   help="Include content/snippet in summarized citations")
    p.add_argument("--adaptive-budget", action=argparse.BooleanOptionalAction, default=None,
                   help="[EXPERIMENTAL] Proportional char allocation based on BM25 rank score")
    p.add_argument("--adaptive-budget-fetch-factor", type=int, default=None, metavar="N",
                   help="[EXPERIMENTAL] Generous pre-rank fetch multiplier (default 3)")
    # --- backends ---
    p.add_argument("--searxng-url", default=None, metavar="URL",
                   help="SearXNG base URL")
    p.add_argument("--brave-api-key", default=None, metavar="KEY")
    p.add_argument("--tavily-api-key", default=None, metavar="KEY")
    p.add_argument("--exa-api-key", default=None, metavar="KEY")
    p.add_argument("--serpapi-api-key", default=None, metavar="KEY")
    p.add_argument("--serpapi-engine", default=None, metavar="ENGINE",
                   help="SerpAPI engine (default: google)")
    p.add_argument("--serpapi-gl", default=None, metavar="CODE",
                   help="SerpAPI country code")
    p.add_argument("--serpapi-hl", default=None, metavar="CODE",
                   help="SerpAPI language code")
    # --- llm ---
    p.add_argument("--llm-enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="Enable LLM features (expansion, summarization, reranking)")
    p.add_argument("--llm-base-url", default=None, metavar="URL",
                   help="OpenAI-compatible API base URL")
    p.add_argument("--llm-api-key", default=None, metavar="KEY")
    p.add_argument("--llm-model", default=None, metavar="MODEL",
                   help="Model name to use for LLM calls")
    p.add_argument("--llm-timeout", type=int, default=None, metavar="SEC",
                   help="Timeout for LLM requests in seconds")
    p.add_argument("--llm-expansion-enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="Auto-expand single queries into complementary variants")
    p.add_argument("--llm-summarization-enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="Include Markdown summary with citations in query output")
    p.add_argument("--llm-rerank-enabled", action=argparse.BooleanOptionalAction, default=None,
                   help="LLM-assisted reranking (deterministic BM25 always active)")
    p.add_argument("--llm-max-summary-words", type=int, default=None, metavar="N",
                   help="Max words in LLM summary (0 = derived from budget)")
    p.add_argument("--llm-input-budget-factor", type=int, default=None, metavar="N",
                   help="LLM input budget = max_query_budget × factor")
    return p.parse_args()


def _apply_args(cfg: Config, args: argparse.Namespace) -> None:
    """Override config values from CLI args (only args explicitly provided, i.e. not None)."""
    a = args
    # server
    if a.default_backend is not None:
        cfg.backends.default = a.default_backend
    if a.max_download_mb is not None:
        cfg.server.max_download_mb = a.max_download_mb
    if a.max_result_length is not None:
        cfg.server.max_result_length = a.max_result_length
    if a.search_timeout is not None:
        cfg.server.search_timeout = a.search_timeout
    if a.oversampling_factor is not None:
        cfg.server.oversampling_factor = a.oversampling_factor
    if a.auto_recovery_fetch is not None:
        cfg.server.auto_recovery_fetch = a.auto_recovery_fetch
    if a.max_total_results is not None:
        cfg.server.max_total_results = a.max_total_results
    if a.max_query_budget is not None:
        cfg.server.max_query_budget = a.max_query_budget
    if a.max_search_queries is not None:
        cfg.server.max_search_queries = a.max_search_queries
    if a.results_per_query is not None:
        cfg.server.results_per_query = a.results_per_query
    if a.debug is not None:
        cfg.server.debug = a.debug
    if a.log_file is not None:
        cfg.server.log_file = a.log_file
    if a.trace is not None:
        cfg.server.trace = a.trace
    if a.adaptive_budget is not None:
        cfg.server.adaptive_budget = a.adaptive_budget
    if a.adaptive_budget_fetch_factor is not None:
        cfg.server.adaptive_budget_fetch_factor = a.adaptive_budget_fetch_factor
    # backends
    if a.searxng_url is not None:
        cfg.backends.searxng.url = a.searxng_url
    if a.brave_api_key is not None:
        cfg.backends.brave.api_key = a.brave_api_key
    if a.tavily_api_key is not None:
        cfg.backends.tavily.api_key = a.tavily_api_key
    if a.exa_api_key is not None:
        cfg.backends.exa.api_key = a.exa_api_key
    if a.serpapi_api_key is not None:
        cfg.backends.serpapi.api_key = a.serpapi_api_key
    if a.serpapi_engine is not None:
        cfg.backends.serpapi.engine = a.serpapi_engine
    if a.serpapi_gl is not None:
        cfg.backends.serpapi.gl = a.serpapi_gl
    if a.serpapi_hl is not None:
        cfg.backends.serpapi.hl = a.serpapi_hl
    # llm
    if a.llm_enabled is not None:
        cfg.llm.enabled = a.llm_enabled
    if a.llm_base_url is not None:
        cfg.llm.base_url = a.llm_base_url
    if a.llm_api_key is not None:
        cfg.llm.api_key = a.llm_api_key
    if a.llm_model is not None:
        cfg.llm.model = a.llm_model
    if a.llm_timeout is not None:
        cfg.llm.timeout = a.llm_timeout
    if a.llm_expansion_enabled is not None:
        cfg.llm.expansion_enabled = a.llm_expansion_enabled
    if a.llm_summarization_enabled is not None:
        cfg.llm.summarization_enabled = a.llm_summarization_enabled
    if a.llm_rerank_enabled is not None:
        cfg.llm.llm_rerank_enabled = a.llm_rerank_enabled
    if a.llm_max_summary_words is not None:
        cfg.llm.max_summary_words = a.llm_max_summary_words
    if a.llm_input_budget_factor is not None:
        cfg.llm.input_budget_factor = a.llm_input_budget_factor


def load_config(args: argparse.Namespace | None = None) -> Config:
    """Load config from toml file (if found), apply env overrides, then CLI args."""
    toml_path = _find_config_file()
    if toml_path:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        cfg = Config.model_validate(data)
    else:
        cfg = Config()
    _apply_env(cfg)
    if args is not None:
        _apply_args(cfg, args)
    return cfg
