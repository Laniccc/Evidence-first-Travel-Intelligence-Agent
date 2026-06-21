from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Evidence-first Travel Intelligence Agent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-v4-pro"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-pro"
    llm_mode: Literal["auto", "mock", "anthropic"] = "auto"

    tool_mode: Literal["mock", "real", "hybrid"] = "hybrid"
    place_resolution_use_mock: bool = False
    enable_real_weather: bool = False
    enable_real_places: bool = False
    enable_real_official_page: bool = False
    mcp_enabled: bool = False
    real_tool_timeout_seconds: float = 8.0
    real_tool_cache_ttl_seconds: int = 3600

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
        "Japan": ["Tokyo", "Kyoto", "Osaka", "Nara", "Sapporo", "Fukuoka", "Okinawa", "Hakone", "Nagoya", "Hiroshima"],
        "China": ["Beijing", "Shanghai", "Hangzhou", "Suzhou", "Xi'an", "Chengdu", "Chongqing", "Guangzhou", "Shenzhen", "Nanjing", "Xiamen", "Qingdao"],
        "South Korea": ["Seoul", "Busan", "Jeju", "Gyeongju", "Incheon", "Daegu"],
    }

    def llm_api_key(self) -> str | None:
        return self.deepseek_api_key or self.anthropic_api_key

    def llm_model(self) -> str:
        return self.deepseek_model or self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
