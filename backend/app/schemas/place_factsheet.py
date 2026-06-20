from pydantic import BaseModel, Field


class PlaceFactSheet(BaseModel):
    place_name: str
    country: str | None = None
    city: str | None = None
    official_hours: str | None = None
    ticket_price: str | None = None
    reservation_policy: str | None = None
    address: str | None = None
    transit_summary: str | None = None
    weather: str | None = None
    crowd_risk: float | None = None
    accessibility: float | None = None
    food_nearby: str | None = None
    walking_intensity: float | None = None
    transport_convenience: float | None = None
    first_timer_fit: float | None = None
    source_ids: dict[str, list[str]] = Field(default_factory=dict)
    confidence: float = 0.0

    def has_field(self, field: str) -> bool:
        val = getattr(self, field, None)
        if val is None:
            return False
        if isinstance(val, float):
            return True
        return bool(str(val).strip())

    def field_source_ids(self, field: str) -> list[str]:
        return self.source_ids.get(field, [])
