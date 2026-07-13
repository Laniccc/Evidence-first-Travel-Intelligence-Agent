"""Confidence calculations for evidence-backed Agent results."""

from typing import Any


class ConfidenceCalculator:
    @staticmethod
    def from_evidence(evidence_list: list[Any]) -> float:
        if not evidence_list:
            return 0.0
        weighted = []
        for evidence in evidence_list:
            claim_confidences = [claim.confidence for claim in evidence.claims] or [evidence.confidence]
            average_claim_confidence = sum(claim_confidences) / len(claim_confidences)
            weighted.append((average_claim_confidence + evidence.confidence) / 2)
        return round(sum(weighted) / len(weighted), 3)

    @staticmethod
    def combine(*values: float | None) -> float:
        numbers = [value for value in values if value is not None]
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 3)
