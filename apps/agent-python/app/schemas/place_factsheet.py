from typing import Any

from pydantic import BaseModel, Field


class FactValue(BaseModel):
    field: str
    value: Any
    source_ids: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    limitations: list[str] = Field(default_factory=list)


FIELD_SUMMARY_ALIAS = {
    "official_hours": "opening_hours",
    "reservation_policy": "reservation_policy",
}


SUMMARY_FIELDS = [
    "official_hours",
    "ticket_price",
    "reservation_policy",
    "address",
    "transit_summary",
    "weather",
    "crowd_risk",
    "walking_intensity",
    "accessibility",
    "food_nearby",
    "transport_convenience",
    "first_timer_fit",
]


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
    field_facts: dict[str, FactValue] = Field(default_factory=dict)
    confidence: float = 0.0

    def has_field(self, field: str) -> bool:
        if field in self.field_facts:
            return True
        val = getattr(self, field, None)
        if val is None:
            return False
        if isinstance(val, float):
            return True
        return bool(str(val).strip())

    def field_source_ids(self, field: str) -> list[str]:
        if field in self.field_facts:
            return self.field_facts[field].source_ids
        return self.source_ids.get(field, [])

    def get_fact_value(self, field: str) -> Any:
        if field in self.field_facts:
            return self.field_facts[field].value
        return getattr(self, field, None)

    def to_field_evidence_summary(self) -> list[dict]:
        rows: list[dict] = []
        for field in SUMMARY_FIELDS:
            fact = self.field_facts.get(field)
            if not fact and not self.has_field(field):
                continue
            if fact:
                out_field = FIELD_SUMMARY_ALIAS.get(field, field)
                rows.append(
                    {
                        "field": out_field,
                        "value": fact.value,
                        "source_ids": fact.source_ids,
                        "source_names": fact.source_names,
                        "source_types": fact.source_types,
                        "confidence": fact.confidence,
                        "limitations": fact.limitations,
                    }
                )
            else:
                val = getattr(self, field, None)
                if val is not None:
                    out_field = FIELD_SUMMARY_ALIAS.get(field, field)
                    rows.append(
                        {
                            "field": out_field,
                            "value": val,
                            "source_ids": self.source_ids.get(field, []),
                            "source_names": [],
                            "source_types": [],
                            "confidence": self.confidence,
                            "limitations": ["Limited source metadata for aggregated field."],
                        }
                    )
        return rows
