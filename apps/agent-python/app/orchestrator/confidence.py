from app.schemas.evidence import Evidence


class ConfidenceCalculator:
    @staticmethod
    def from_evidence(evidence_list: list[Evidence]) -> float:
        if not evidence_list:
            return 0.0
        weighted = []
        for ev in evidence_list:
            claim_conf = [c.confidence for c in ev.claims] or [ev.confidence]
            avg_claim = sum(claim_conf) / len(claim_conf)
            weighted.append((avg_claim + ev.confidence) / 2)
        return round(sum(weighted) / len(weighted), 3)

    @staticmethod
    def combine(*values: float | None) -> float:
        nums = [v for v in values if v is not None]
        if not nums:
            return 0.0
        return round(sum(nums) / len(nums), 3)
