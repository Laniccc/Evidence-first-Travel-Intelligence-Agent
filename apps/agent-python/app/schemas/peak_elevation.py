"""Structured peak elevation facts for geo_fact LOOKUP."""

from __future__ import annotations

from pydantic import BaseModel, Field

ElevationGranularity = str  # exact_numeric | range_only | unrelated_geo | none


class PeakElevationFact(BaseModel):
    place_name: str = ""
    peak_name: str = ""
    elevation_m: float | None = None
    relation: str = "main_peak"  # highest_peak | main_peak | scenic_spot
    source_name: str = ""
    source_url: str | None = None
    confidence: float = 0.5
    raw_text: str = ""


class PeakElevationTable(BaseModel):
    place_name: str = ""
    highest_peak: str | None = None
    peaks: list[PeakElevationFact] = Field(default_factory=list)
    coverage_quality: str = "none"
    value_granularity: str = "none"
    limitations: list[str] = Field(default_factory=list)
