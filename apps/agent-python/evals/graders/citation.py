"""Claim citation and abstention metrics."""

from pydantic import BaseModel


class CitationCaseResult(BaseModel):
    case_id: str
    expected_supported: bool
    actual_supported: bool
    expected_abstain: bool
    actual_abstain: bool


class CitationMetrics(BaseModel):
    case_count: int
    citation_precision: float
    unsupported_hard_facts: int
    abstention_precision: float


def grade_citations(cases: list[CitationCaseResult]) -> CitationMetrics:
    predicted_supported = [item for item in cases if item.actual_supported]
    predicted_abstain = [item for item in cases if item.actual_abstain]
    return CitationMetrics(
        case_count=len(cases),
        citation_precision=(
            sum(item.expected_supported for item in predicted_supported)
            / len(predicted_supported)
            if predicted_supported
            else 1.0
        ),
        unsupported_hard_facts=sum(
            item.actual_supported and not item.expected_supported for item in cases
        ),
        abstention_precision=(
            sum(item.expected_abstain for item in predicted_abstain)
            / len(predicted_abstain)
            if predicted_abstain
            else 1.0
        ),
    )


__all__ = ["CitationCaseResult", "CitationMetrics", "grade_citations"]
