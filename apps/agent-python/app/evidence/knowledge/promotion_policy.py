"""Operator-owned retention policy. Software licensing never enables storage."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionPolicy:
    version: str = "baidu-extractive-v1"
    storage_enabled: bool = False
    address_ttl_seconds: int = 7 * 86400
    hours_ttl_seconds: int = 3600
    source_max_age_seconds: int = 3600

    def storage_allowed(self, provider: str, fact_type: str) -> bool:
        return self.storage_enabled and provider == "baidu-map" and fact_type in {
            "general_description", "opening_hours"}

    def ttl(self, fact_type: str) -> int:
        return self.address_ttl_seconds if fact_type == "general_description" else self.hours_ttl_seconds


ALLOWED_POINTERS = {"general_description": "/address", "opening_hours": "/detail_info/shop_hours"}
