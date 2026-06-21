from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.place_context import PlaceContext


class PlaceResolutionSource(str, Enum):
    SESSION_MEMORY = "session_memory"
    LOCAL_CACHE = "local_cache"
    REAL_PLACES = "real_places"
    MCP_PLACES = "mcp_places"
    LLM_GEocode = "llm_geocode"
    MOCK_CATALOG = "mock_catalog"
    EXTRACTOR = "extractor"


class PlaceCandidate(BaseModel):
    """Resolved or partially resolved geographic entity — not evidence-backed facts."""

    mention: str
    canonical_name: str | None = None
    country: str | None = None
    city: str | None = None
    region: str | None = None
    place_type: str = "unknown"  # city | country | poi | region
    confidence: float = 0.5
    resolution_source: PlaceResolutionSource = PlaceResolutionSource.EXTRACTOR
    coordinates: dict | None = None
    metadata: dict = Field(default_factory=dict)

    @property
    def is_poi(self) -> bool:
        return self.place_type in {"poi", "place"}

    @property
    def is_city(self) -> bool:
        return self.place_type == "city"

    def to_place_context(self) -> PlaceContext:
        return PlaceContext(
            original_name=self.mention,
            canonical_name=self.canonical_name or self.mention,
            country=self.country,
            city=self.city,
            confidence=self.confidence,
            source=self.resolution_source.value,
        )
