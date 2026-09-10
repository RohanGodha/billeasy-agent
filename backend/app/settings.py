"""Centralised application settings backed by pydantic-settings.

All configuration must flow through this module — no scattered os.environ reads.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "counter-copilot"
    app_env: str = "development"
    app_password: str = "shared"
    app_cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # --- LLM ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    gemini_embed_model: str = "text-embedding-004"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    # Effort trades thinking depth against latency. This agent is interactive — an
    # Area Manager is waiting on the plan — so it runs low by default. Raise to
    # "high" if you want deeper planning and can afford the extra seconds.
    anthropic_effort: str = "low"

    # --- Data ---
    databricks_host: str = ""
    databricks_http_path: str = ""
    databricks_token: str = ""
    databricks_catalog: str = "counter_copilot"
    databricks_schema: str = "core"
    databricks_timeout_seconds: float = 5.0

    sqlite_path: str = "./data/app.db"
    chroma_dir: str = "./data/chroma"

    # --- Agent ---
    # A standard plan is 5 steps, and a critic-forced replan consumes an iteration. At 6
    # there was effectively no headroom: a single replan truncated the plan and the
    # synthesizer ran on partial tool output. 10 leaves room for replans while still
    # bounding a runaway loop. Truncation is now reported rather than silent.
    agent_max_iterations: int = 10
    agent_top_k_candidates: int = 10
    agent_tool_timeout_seconds: float = 15.0

    # --- Keep-alive ---
    self_ping_url: str = ""
    self_ping_interval_seconds: int = 600

    # --- Tool cache ---
    # How long a cached tool result is trusted before re-computing. The demo warehouse
    # is an immutable seed, so a process-lifetime cache would be safe; this still bounds
    # staleness if real data ever refreshes. 0 disables caching entirely.
    tool_cache_ttl_seconds: int = 300
    # Rocchio-style feedback retrieval: how many feedback terms are reused across turns
    # and how many times each is repeated in the query to boost its BM25 contribution.
    rocchio_max_feedback_terms: int = 4
    rocchio_expansion_repeats: int = 2

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @property
    def sqlite_abs_path(self) -> Path:
        path = Path(self.sqlite_path)
        if not path.is_absolute():
            path = (Path(__file__).resolve().parent.parent / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chroma_abs_dir(self) -> Path:
        path = Path(self.chroma_dir)
        if not path.is_absolute():
            path = (Path(__file__).resolve().parent.parent / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def databricks_enabled(self) -> bool:
        return bool(self.databricks_host and self.databricks_token and self.databricks_http_path)

    @property
    def has_any_llm(self) -> bool:
        return bool(self.gemini_api_key or self.groq_api_key or self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
