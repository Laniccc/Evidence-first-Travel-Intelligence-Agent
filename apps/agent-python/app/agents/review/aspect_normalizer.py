from app.schemas.review import ReviewAspect


class AspectNormalizer:
    @staticmethod
    def normalize(aspects: list[ReviewAspect]) -> list[ReviewAspect]:
        merged: dict[str, ReviewAspect] = {}
        for aspect in aspects:
            key = aspect.aspect.value
            if key not in merged:
                merged[key] = aspect
                continue
            existing = merged[key]
            existing.frequency = max(existing.frequency, aspect.frequency)
            existing.confidence = max(existing.confidence, aspect.confidence)
            existing.evidence_examples = list(dict.fromkeys(existing.evidence_examples + aspect.evidence_examples))[:3]
        for aspect in merged.values():
            aspect.evidence_examples = aspect.evidence_examples[:3]
        return list(merged.values())
