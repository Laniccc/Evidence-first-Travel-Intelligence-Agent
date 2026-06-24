"""S7 curated evidence output for S8 composition."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CuratedClaimRow(BaseModel):
    claim_type: str
    value: str
    evidence_id: str
    source_name: str
    source_url: str | None = None
    confidence: float = 0.5
    relevance_score: float = 0.5
    rationale: str = ""
    place_name: str | None = None


class EvidenceBrief(BaseModel):
    target_label: str = "目的地"
    curated_claims: list[CuratedClaimRow] = Field(default_factory=list)
    fact_decompositions: list[dict] = Field(default_factory=list)
    excluded_evidence_ids: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    conflict_notes: list[str] = Field(default_factory=list)
    overall_confidence: float = 0.0
    curation_notes: list[str] = Field(default_factory=list)
    per_place: list["EvidenceBrief"] = Field(default_factory=list)

    def to_field_evidence_summary(self) -> list[dict]:
        rows: list[dict] = []
        for claim in self.curated_claims:
            rows.append(
                {
                    "field": claim.claim_type,
                    "value": claim.value,
                    "source_ids": [claim.evidence_id],
                    "confidence": claim.confidence,
                    "source_names": [claim.source_name],
                    "relevance_score": claim.relevance_score,
                    "place_name": claim.place_name,
                }
            )
        for place_brief in self.per_place:
            rows.extend(place_brief.to_field_evidence_summary())
        return rows
