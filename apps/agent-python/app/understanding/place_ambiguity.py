"""Place ambiguity metadata — preserved by S2, gated by S3, resolved in S5."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EntityLabel = Literal[
    "primary_subject",
    "place_mention",
    "ambiguous_place_candidate",
    "resolved_place",
    "region_anchor",
    "city_anchor",
    "alternate_name",
]


class PlaceAmbiguityCandidate(BaseModel):
    name: str
    region: str | None = None
    city: str | None = None
    note: str | None = None
    confidence: float = 0.5


class PlaceAmbiguityInfo(BaseModel):
    """S2 preserves ambiguity; S3 forwards to contract; S5 resolves via evidence."""

    is_ambiguous: bool = False
    reason: str | None = None
    candidates: list[PlaceAmbiguityCandidate] = Field(default_factory=list)
