"""Deep Research Agent — configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- App --
    app_name: str = "Deep Research Agent Platform"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # -- LLM --
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-v4-flash"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    llm_mode: Literal["anthropic"] = "anthropic"
    llm_request_timeout_seconds: float = 120.0
    llm_empty_response_retries: int = 3
    llm_max_output_tokens: int = 4096
    llm_json_min_tokens: int = 1536
    llm_disable_thinking: bool = True

    # -- Tool Mode --
    tool_mode: Literal["real", "hybrid"] = "hybrid"

    # -- MCP Search (open-websearch) --
    mcp_enabled: bool = True
    mcp_search_enabled: bool = True
    mcp_search_server_url: str = "http://127.0.0.1:3210"
    mcp_search_default_engine: str = "baidu"
    mcp_search_fallback_engines: str = "sogou,bing"
    mcp_search_timeout_seconds: float = 30.0

    # -- RAG (ChromaDB) --
    chroma_db_path: str = "./data/chroma"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_enabled: bool = True

    # -- Agent Core Store --
    agent_core_store_backend: Literal["memory", "sqlite"] = "memory"
    agent_core_store_sqlite_path: str = "./data/agent_core_store.sqlite3"

    # -- Safety Limits --
    max_total_searches: int = 30
    max_total_fetches: int = 20
    max_run_duration_seconds: int = 300

    @field_validator("deepseek_api_key", "anthropic_api_key", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    def llm_api_key(self) -> str | None:
        return self.deepseek_api_key or self.anthropic_api_key

    def llm_model(self) -> str:
        return self.deepseek_model or self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
