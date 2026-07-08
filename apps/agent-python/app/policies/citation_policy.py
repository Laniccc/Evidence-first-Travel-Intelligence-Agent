from pydantic import BaseModel, Field


class CitationPolicy(BaseModel):
    """Rules for S8 answer composition — no unsupported facts."""

    forbid_invented_facts: bool = True
    require_evidence_citations: bool = True
    allowed_claim_types: list[str] = Field(
        default_factory=lambda: [
            "travel_advice",
            "seasonality",
            "best_time_to_visit",
            "opening_hours",
            "ticket_price",
            "reservation",
            "transit",
            "weather",
            "crowd",
            "review_aspect",
        ]
    )
    forbidden_topics_without_evidence: list[str] = Field(
        default_factory=lambda: [
            "exact opening hours",
            "ticket price",
            "live weather",
            "current crowd level",
            "reservation availability",
        ]
    )

    def to_prompt_rules(self) -> list[str]:
        rules = [
            "Only state facts that appear in the provided evidence claims.",
            "Do NOT invent opening hours, ticket prices, live weather, or crowd levels.",
            "Every substantive claim must map to a cited_evidence_id from the input bundle.",
            "Include limitations from the input; do not contradict them.",
        ]
        if self.require_evidence_citations:
            rules.append(
                "cited_evidence_ids must copy evidence_id values exactly from curated_claims "
                "(full UUID strings — do not shorten or invent ids)."
            )
            rules.append(
                "When making factual claims, cited_evidence_ids must be non-empty and "
                "each id must appear in input evidence_ids."
            )
        return rules

    @classmethod
    def for_composition(cls) -> "CitationPolicy":
        return cls()
