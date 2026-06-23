"""Resolve conflicting evidence for the same claim (S7)."""

from __future__ import annotations

import re

from app.orchestrator.evidence_scorer import EvidenceScore
from app.schemas.evidence_decision_report import EvidenceConflict

_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)")


class EvidenceConflictResolver:
    SOURCE_PRIORITY = [
        "official",
        "tourism_board",
        "ticket_platform",
        "map",
        "review_platform",
        "public_web",
        "search_result",
        "model_prior",
        "fallback",
    ]

    def resolve(
        self,
        claim_type: str,
        scores: list[EvidenceScore],
    ) -> tuple[list[EvidenceConflict], str | None]:
        if len(scores) < 2:
            return [], (scores[0].evidence_id if scores else None)

        conflicts: list[EvidenceConflict] = []
        if claim_type == "ticket_price":
            prices = self._extract_prices(scores)
            if len(prices) >= 2 and max(prices) - min(prices) > 1:
                preferred = self._pick_preferred(scores)
                conflicts.append(
                    EvidenceConflict(
                        claim_type=claim_type,
                        conflict_type="price_mismatch",
                        evidence_ids=[s.evidence_id for s in scores[:5]],
                        preferred_evidence_id=preferred,
                        conflict_note=(
                            f"多个来源票价不一致（约 {min(prices):.0f}–{max(prices):.0f} 元），"
                            "优先采用更可靠来源，其余作为候选。"
                        ),
                    )
                )
                return conflicts, preferred

        values = {self._normalize(s.claim_value) for s in scores}
        if len(values) > 1:
            preferred = self._pick_preferred(scores)
            conflicts.append(
                EvidenceConflict(
                    claim_type=claim_type,
                    conflict_type="value_mismatch",
                    evidence_ids=[s.evidence_id for s in scores[:5]],
                    preferred_evidence_id=preferred,
                    conflict_note="多来源对该 claim 给出不同表述，保留差异并标注限制。",
                )
            )
            return conflicts, preferred

        return conflicts, scores[0].evidence_id

    def _pick_preferred(self, scores: list[EvidenceScore]) -> str:
        def rank(s: EvidenceScore) -> tuple:
            src = (s.source_type or "").lower()
            pri = 99
            for i, key in enumerate(self.SOURCE_PRIORITY):
                if key in src or key in (s.source_name or "").lower():
                    pri = i
                    break
            return (pri, -s.total_score)

        return sorted(scores, key=rank)[0].evidence_id

    @staticmethod
    def _extract_prices(scores: list[EvidenceScore]) -> list[float]:
        out: list[float] = []
        for s in scores:
            for m in _PRICE_RE.findall(s.claim_value):
                try:
                    v = float(m)
                    if 1 <= v <= 5000:
                        out.append(v)
                except ValueError:
                    continue
        return out

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", "", text.lower())[:80]
