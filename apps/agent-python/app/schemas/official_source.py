"""Official source candidate schemas for S5 discovery and S7 judgement."""

from __future__ import annotations

from pydantic import BaseModel, Field

# source_class values (str constants, not a strict enum)
SOURCE_CLASS_OFFICIAL_GOVERNMENT = "official_government"
SOURCE_CLASS_TOURISM_BOARD_OFFICIAL = "tourism_board_official"
SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL = "scenic_operator_official"
SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE = "scenic_operator_official_candidate"
SOURCE_CLASS_OFFICIAL_ACCOUNT_CANDIDATE = "official_account_candidate"
SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE = "authorized_platform_candidate"
SOURCE_CLASS_MAP_PROVIDER_CANDIDATE = "map_provider_candidate"
SOURCE_CLASS_REVIEW_PLATFORM = "review_platform"
SOURCE_CLASS_OTA_PLATFORM = "ota_platform"
SOURCE_CLASS_THIRD_PARTY_PLATFORM = "third_party_platform"
SOURCE_CLASS_SEO_CONTENT_SITE = "seo_content_site"
SOURCE_CLASS_NOT_OFFICIAL = "not_official"
SOURCE_CLASS_UNKNOWN = "unknown"

OFFICIAL_SOURCE_CLASSES = frozenset(
    {
        SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
        SOURCE_CLASS_OFFICIAL_ACCOUNT_CANDIDATE,
    }
)

STRONG_OFFICIAL_SOURCE_CLASSES = frozenset(
    {
        SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
    }
)

PLATFORM_SOURCE_CLASSES = frozenset(
    {
        SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE,
        SOURCE_CLASS_MAP_PROVIDER_CANDIDATE,
        SOURCE_CLASS_REVIEW_PLATFORM,
        SOURCE_CLASS_OTA_PLATFORM,
        SOURCE_CLASS_THIRD_PARTY_PLATFORM,
    }
)


def is_official_source_class(source_class: str) -> bool:
    return source_class in OFFICIAL_SOURCE_CLASSES


def is_platform_source_class(source_class: str) -> bool:
    return source_class in PLATFORM_SOURCE_CLASSES


class OfficialSourceCandidate(BaseModel):
    url: str
    domain: str
    title: str | None = None
    source_class: str = SOURCE_CLASS_UNKNOWN
    official_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    organization_name: str | None = None
    supports_claim_types: list[str] = Field(default_factory=list)
    supporting_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    discovered_by: str | None = None
    verified_by: str | None = None
    page_excerpt: str | None = None
    has_ticket_info: bool = False
    has_opening_hours: bool = False
    has_notice_info: bool = False
    has_contact_info: bool = False
    has_about_or_footer_info: bool = False
    claim_relevance_hints: dict[str, float] = Field(default_factory=dict)


class OfficialSourceDiscoveryResult(BaseModel):
    place_name: str
    claim_type: str | None = None
    candidates: list[OfficialSourceCandidate] = Field(default_factory=list)
    search_queries_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
