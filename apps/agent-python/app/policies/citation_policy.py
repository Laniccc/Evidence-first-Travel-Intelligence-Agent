"""Citation policy — rules for evidence-based answer composition."""

from pydantic import BaseModel, Field


class CitationPolicy(BaseModel):
    """Rules for answer composition — no unsupported facts."""

    forbid_invented_facts: bool = True
    require_evidence_citations: bool = True
    allowed_claim_types: list[str] = Field(
        default_factory=lambda: [
            "fact",
            "data_point",
            "statistical_claim",
            "analysis",
            "opinion",
            "summary",
        ]
    )
    forbidden_topics_without_evidence: list[str] = Field(
        default_factory=lambda: [
            "exact numerical data",
            "statistics without source",
            "price information",
            "live or real-time data",
            "unverifiable predictions",
        ]
    )

    def to_prompt_rules(self) -> list[str]:
        rules = [
            "Only state facts that appear in the provided evidence claims.",
            "Do NOT invent statistics, numerical data, or predictions.",
            "Every substantive claim must map to a source URL from the input evidence.",
            "Include limitations from the input; do not contradict them.",
        ]
        if self.require_evidence_citations:
            rules.append(
                "When making factual claims, cite source URLs. Each claim must "
                "reference at least one evidence record."
            )
        return rules

    @classmethod
    def for_composition(cls) -> "CitationPolicy":
        return cls()
