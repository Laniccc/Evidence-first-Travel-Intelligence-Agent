from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Evidence-first Travel Intelligence Agent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-v4-flash"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    llm_mode: Literal["auto", "mock", "anthropic"] = "auto"

    tool_mode: Literal["mock", "real", "hybrid"] = "hybrid"
    place_resolution_use_mock: bool = False
    enable_real_weather: bool = False
    enable_real_places: bool = False
    enable_real_official_page: bool = False
    mcp_enabled: bool = True
    real_tool_timeout_seconds: float = 8.0
    real_tool_cache_ttl_seconds: int = 3600

    mcp_search_enabled: bool = False
    mcp_search_server_url: str = ""
    mcp_browser_enabled: bool = False
    mcp_browser_server_url: str = ""
    mcp_osm_enabled: bool = False
    mcp_osm_server_url: str = ""
    mcp_openmeteo_enabled: bool = False
    mcp_openmeteo_server_url: str = ""
    mcp_wikipedia_enabled: bool = False
    mcp_wikipedia_server_url: str = ""
    mcp_wikidata_enabled: bool = False
    mcp_wikidata_server_url: str = ""
    mcp_sqlite_enabled: bool = False
    mcp_sqlite_server_url: str = ""
    mcp_sqlite_readonly: bool = True
    mcp_timeout_seconds: float = 10.0
    mcp_max_result_chars: int = 6000
    mcp_max_tool_calls_per_state: int = 5
    official_page_allowed_domains: str = ""
    browser_allowed_domains: str = ""

    weather_api_key: str | None = None
    places_api_key: str | None = None

    official_page_whitelist: dict[str, str] = {
        "Kiyomizu-dera": "https://www.kyoto-travel.jp/en/shrine_temple/100.html",
        "Fushimi Inari": "https://inari.jp/en/",
        "Senso-ji": "https://www.senso-ji.jp/english/",
        "Tokyo Skytree": "https://www.tokyo-skytree.jp/en/",
        "Forbidden City": "https://www.dpm.org.cn/",
    }

    evidence_confidence_threshold: float = 0.55
    low_confidence_threshold: float = 0.35

    supported_countries: list[str] = ["Japan", "China", "South Korea"]
    supported_cities: dict[str, list[str]] = {
        "Japan": ["Tokyo", "Kyoto", "Osaka", "Nara", "Sapporo", "Fukuoka", "Okinawa", "Hakone", "Nagoya", "Hiroshima", "Okayama"],
        "China": ["Beijing", "Shanghai", "Hangzhou", "Suzhou", "Xi'an", "Chengdu", "Chongqing", "Guangzhou", "Shenzhen", "Nanjing", "Xiamen", "Qingdao"],
        "South Korea": ["Seoul", "Busan", "Jeju", "Gyeongju", "Incheon", "Daegu"],
    }

    @field_validator("deepseek_api_key", "anthropic_api_key", "weather_api_key", "places_api_key", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    def llm_api_key(self) -> str | None:
        return self.deepseek_api_key or self.anthropic_api_key

    def llm_model(self) -> str:
        return self.deepseek_model or self.anthropic_model

    def official_page_domain_allowlist(self) -> list[str]:
        return [d.strip() for d in self.official_page_allowed_domains.split(",") if d.strip()]

    def browser_domain_allowlist(self) -> list[str]:
        return [d.strip() for d in self.browser_allowed_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
