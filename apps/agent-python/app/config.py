from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Evidence-first Travel Intelligence Agent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    agent_service_key: str | None = None
    readiness_requires_qdrant: bool = False
    # Composition-root wiring is deliberately deferred until the full chain is ready.
    agent_runtime_profile: Literal["offline", "online"] = "offline"
    understanding_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    understanding_max_tokens: int = Field(default=1536, ge=128, le=4096)

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-v4-flash"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    llm_mode: Literal["anthropic"] = "anthropic"
    llm_request_timeout_seconds: float = 120.0
    llm_empty_response_retries: int = 3
    llm_max_output_tokens: int = 4096
    llm_planner_max_tokens: int = 2048
    llm_disable_thinking: bool = True
    llm_json_min_tokens: int = 1536

    tool_mode: Literal["real", "hybrid"] = "real"
    place_resolution_use_mock: bool = False
    enable_real_weather: bool = False
    enable_real_places: bool = False
    enable_real_official_page: bool = False
    mcp_enabled: bool = True
    # 总开关：true 时启用下方全部 MCP_*（各服务仍可在 MCP_ENABLE_ALL=false 时单独控制）
    mcp_enable_all: bool = True
    # full=全部已接通的 MCP 子服务 | search_only=仅 search_mcp（推荐） | off=全关子服务
    mcp_profile: Literal["full", "search_only", "off"] = "search_only"
    real_tool_timeout_seconds: float = 8.0
    real_tool_cache_ttl_seconds: int = 3600

    mcp_search_enabled: bool = True
    mcp_search_server_url: str = "http://127.0.0.1:3210"
    mcp_search_transport: str = "open_websearch_http"
    mcp_search_tool_name: str = "search"
    mcp_search_command: str = ""
    mcp_search_args: str = ""
    # open-webSearch: baidu/sogou work better in CN than duckduckgo
    mcp_search_default_engine: str = "baidu"
    # Comma-separated fallback engines when primary returns empty / engine_error (e.g. baidu 302)
    mcp_search_fallback_engines: str = "sogou,bing"
    mcp_search_timeout_seconds: float = 30.0
    mcp_search_use_proxy: bool = False
    mcp_search_proxy_url: str = "http://127.0.0.1:7890"
    mcp_browser_enabled: bool = True
    mcp_browser_server_url: str = ""
    mcp_browser_transport: str = "stdio"
    mcp_browser_command: str = "npx"
    mcp_browser_args: str = "-y,@playwright/mcp@latest"
    mcp_osm_enabled: bool = True
    mcp_osm_server_url: str = ""
    mcp_osm_transport: str = "stdio"
    mcp_osm_command: str = "uvx"
    mcp_osm_args: str = "osm-mcp-server"
    mcp_openmeteo_enabled: bool = True
    mcp_openmeteo_server_url: str = "http://127.0.0.1:3000/mcp"
    mcp_openmeteo_transport: str = "streamable_http"
    mcp_openmeteo_tool_name: str = "weather_forecast"
    mcp_openmeteo_command: str = ""
    mcp_openmeteo_args: str = ""
    mcp_wikipedia_enabled: bool = True
    mcp_wikipedia_server_url: str = ""
    mcp_wikipedia_transport: str = "stdio"
    mcp_wikipedia_command: str = "npx"
    mcp_wikipedia_args: str = "-y,@cyanheads/wikipedia-mcp-server"
    mcp_wikidata_enabled: bool = True
    mcp_wikidata_server_url: str = ""
    mcp_wikidata_transport: str = "stdio"
    mcp_wikidata_command: str = "npx"
    mcp_wikidata_args: str = "-y,mcp-wikidata"
    mcp_sqlite_enabled: bool = True
    mcp_sqlite_server_url: str = ""
    mcp_sqlite_transport: str = "stdio"
    mcp_sqlite_command: str = "npx"
    mcp_sqlite_args: str = "-y,mcp-sqlite,./data/evidence_cache.db"
    mcp_sqlite_readonly: bool = True
    baidu_map_ak: str | None = None
    mcp_baidu_map_enabled: bool = False
    mcp_baidu_map_transport: str = "baidu_streamable_http"
    mcp_baidu_map_server_url: str = "https://mcp.map.baidu.com/mcp"
    mcp_baidu_map_sse_url: str = "https://mcp.map.baidu.com/sse"
    mcp_baidu_map_timeout_seconds: float = 10.0
    mcp_baidu_map_stdio_enabled: bool = False
    mcp_baidu_map_stdio_command: str = "npx"
    mcp_baidu_map_stdio_args: str = "-y,@baidumap/mcp-server-baidu-map"
    mcp_timeout_seconds: float = 10.0
    mcp_browser_timeout_seconds: float = 45.0
    mcp_max_result_chars: int = 6000
    mcp_max_tool_calls_per_state: int = 10
    mcp_max_tool_calls_comparison: int = 14
    evidence_max_gap_rounds: int = 1
    intent_profile_enabled: bool = True
    evidence_gap_max_extra_steps: int = 3
    mcp_http_autostart: bool = True
    mcp_http_autostart_new_window: bool = True
    mcp_http_autostart_kill_stale: bool = True
    mcp_http_autostart_wait_seconds: float = 8.0
    official_page_allowed_domains: str = ""
    browser_allowed_domains: str = ""
    official_source_discovery_enabled: bool = True

    weather_api_key: str | None = None
    places_api_key: str | None = None

    official_page_whitelist: dict[str, str] = {
        "故宫博物院": "https://www.dpm.org.cn/",
        "故宫": "https://www.dpm.org.cn/",
        "Kiyomizu-dera": "https://www.kyoto-travel.jp/en/shrine_temple/100.html",
        "Fushimi Inari": "https://inari.jp/en/",
        "Senso-ji": "https://www.senso-ji.jp/english/",
        "Tokyo Skytree": "https://www.tokyo-skytree.jp/en/",
        "Forbidden City": "https://www.dpm.org.cn/",
    }

    evidence_confidence_threshold: float = 0.55
    low_confidence_threshold: float = 0.35

    # Versioned attraction knowledge corpus (SQLite + FTS5)
    knowledge_db_path: str = "./data/knowledge.sqlite3"
    knowledge_default_ttl_days: int = 30
    knowledge_retrieval_top_k: int = 3

    # Rebuildable dense retrieval index. SQLite remains the authority.
    qdrant_mode: Literal["local", "server"] = "local"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "attraction-facts"
    qdrant_local_path: str = "./data/qdrant"
    embedding_mode: Literal["deterministic", "fastembed"] = "deterministic"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    vector_search_limit: int = 20

    # Agent Core Store
    agent_core_store_backend: Literal["memory", "jsonl", "sqlite"] = "memory"
    agent_core_store_jsonl_path: str = "./data/agent_core_store.jsonl"
    agent_core_store_sqlite_path: str = "./data/agent_core_store.sqlite3"
    agent_run_db_path: str = "./data/agent_runs.sqlite3"

    supported_countries: list[str] = ["Japan", "China", "South Korea"]
    supported_cities: dict[str, list[str]] = {
        "Japan": ["Tokyo", "Kyoto", "Osaka", "Nara", "Sapporo", "Fukuoka", "Okinawa", "Hakone", "Nagoya", "Hiroshima", "Okayama", "Fujikawaguchiko"],
        "China": ["Beijing", "Shanghai", "Hangzhou", "Suzhou", "Xi'an", "Chengdu", "Chongqing", "Guangzhou", "Shenzhen", "Nanjing", "Xiamen", "Qingdao", "Altay", "Lijiang", "Xinjiang", "Ganzi"],
        "South Korea": ["Seoul", "Busan", "Jeju", "Gyeongju", "Incheon", "Daegu"],
    }

    @field_validator(
        "deepseek_api_key",
        "anthropic_api_key",
        "weather_api_key",
        "places_api_key",
        "baidu_map_ak",
        "qdrant_api_key",
        "agent_service_key",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @model_validator(mode="after")
    def _apply_mcp_profile(self) -> Self:
        if not self.mcp_enabled:
            return self
        if self.mcp_profile == "off":
            self.mcp_search_enabled = False
            self.mcp_browser_enabled = False
            self.mcp_osm_enabled = False
            self.mcp_openmeteo_enabled = False
            self.mcp_wikipedia_enabled = False
            self.mcp_wikidata_enabled = False
            self.mcp_sqlite_enabled = False
            self.mcp_baidu_map_enabled = False
            return self
        if self.mcp_profile == "search_only":
            self.mcp_search_enabled = True
            self.mcp_browser_enabled = False
            self.mcp_osm_enabled = False
            self.mcp_openmeteo_enabled = False
            self.mcp_wikipedia_enabled = False
            self.mcp_wikidata_enabled = False
            self.mcp_sqlite_enabled = False
            self.mcp_baidu_map_enabled = False
            return self
        if self.mcp_enable_all or self.mcp_profile == "full":
            from tools.mcp.adapter_status import IMPLEMENTED_MCP_POLICIES

            self.mcp_search_enabled = True
            self.mcp_browser_enabled = "browser_mcp" in IMPLEMENTED_MCP_POLICIES
            self.mcp_osm_enabled = any(
                p in IMPLEMENTED_MCP_POLICIES for p in ("osm_mcp", "places_mcp", "geocode_mcp")
            )
            self.mcp_openmeteo_enabled = any(
                p in IMPLEMENTED_MCP_POLICIES for p in ("openmeteo_mcp", "weather_mcp", "climate_mcp")
            )
            self.mcp_wikipedia_enabled = "wikipedia_mcp" in IMPLEMENTED_MCP_POLICIES
            self.mcp_wikidata_enabled = "wikidata_mcp" in IMPLEMENTED_MCP_POLICIES
            self.mcp_sqlite_enabled = any(
                p in IMPLEMENTED_MCP_POLICIES for p in ("sqlite_mcp", "evidence_store_mcp")
            )
        return self

    def llm_api_key(self) -> str | None:
        return self.deepseek_api_key or self.anthropic_api_key

    def llm_model(self) -> str:
        return self.deepseek_model or self.anthropic_model

    def official_page_domain_allowlist(self) -> list[str]:
        return [d.strip() for d in self.official_page_allowed_domains.split(",") if d.strip()]

    def browser_domain_allowlist(self) -> list[str]:
        return [d.strip() for d in self.browser_allowed_domains.split(",") if d.strip()]

    def baidu_map_mcp_url(self) -> str:
        base = (self.mcp_baidu_map_server_url or "").rstrip("/")
        ak = self.baidu_map_ak or ""
        if not base or not ak:
            return ""
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}ak={ak}"

    def baidu_map_sse_url(self) -> str:
        base = (self.mcp_baidu_map_sse_url or "").rstrip("/")
        ak = self.baidu_map_ak or ""
        if not base or not ak:
            return ""
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}ak={ak}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
