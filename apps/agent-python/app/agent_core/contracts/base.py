"""Base task contract primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agent_core.state.lifecycle import TOPIC_PHASE_ORDER
from app.agent_core.state.models import EvidenceRecord


@dataclass
class ContractCheck:
    status: str
    score: float
    blocking_issues: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    revision_instructions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class TaskContract(Protocol):
    task_class: str
    phase_order: tuple[str, ...]

    def research_plan(self, query: str, target: str | None = None) -> dict[str, Any]: ...

    def review_evidence(self, evidence: list[EvidenceRecord], *, query: str) -> dict[str, Any]: ...

    def decide_claim(self, review: dict[str, Any], *, query: str, target: str | None = None) -> dict[str, Any]: ...

    def check_claim_decision(self, decision: dict[str, Any]) -> ContractCheck: ...

    def compose_answer(self, decision: dict[str, Any], *, query: str) -> str: ...


class BaseTaskContract:
    task_class = "general_lookup"
    phase_order = tuple(TOPIC_PHASE_ORDER)

    def research_plan(self, query: str, target: str | None = None) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "query": query,
            "target": target,
            "source_families": ["official", "platform", "map", "web_reference"],
            "objectives": [{"claim_type": self.task_class, "query": query}],
            "stop_conditions": ["at_least_one_relevant_source_or_explicit_gap"],
        }

    def review_evidence(self, evidence: list[EvidenceRecord], *, query: str) -> dict[str, Any]:
        adopted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen_texts: set[str] = set()

        for ev in evidence:
            text = _claim_text(ev)
            if not text or not text.strip():
                rejected.append(_reject(ev, "empty_evidence"))
                continue
            if "no search hits" in text.lower() or "returned no results" in text.lower():
                rejected.append(_reject(ev, "empty_search_result"))
                continue

            # Basic dedup: skip near-duplicate texts (same first 80 chars)
            text_key = text[:80].strip()
            if text_key in seen_texts:
                rejected.append(_reject(ev, "duplicate_evidence"))
                continue
            seen_texts.add(text_key)

            adopted.append({
                "evidence_id": ev.evidence_id,
                "source_name": ev.source_name,
                "source_type": ev.source_type,
                "claim_summary": text,
                "reliability": ev.reliability,
            })

        # Group by source_type for structured review
        by_type: dict[str, list[dict]] = {}
        for a in adopted:
            by_type.setdefault(a.get("source_type", "unknown"), []).append(a)

        # Sort within each group by reliability
        _rel_order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        for group in by_type.values():
            group.sort(key=lambda x: _rel_order.get(x.get("reliability", "unknown"), 0), reverse=True)

        # Limit to top 5 total to avoid noise
        top = adopted[:5] if len(adopted) > 5 else adopted

        return {
            "adopted_candidates": adopted,
            "rejected_candidates": rejected,
            "top_candidates": top,
            "by_source_type": {k: v[:3] for k, v in by_type.items()},
            "missing_fields": [] if adopted else ["verified_fact"],
            "contradictions": [],
            "next_gap_requests": [] if adopted else [{"claim_type": self.task_class, "reason": "no adopted evidence"}],
        }

    def decide_claim(self, review: dict[str, Any], *, query: str, target: str | None = None) -> dict[str, Any]:
        adopted = list(review.get("adopted_candidates") or [])
        return {
            "claim": query,
            "target": target,
            "adopted_value": adopted[0]["claim_summary"] if adopted else None,
            "confidence": "medium" if adopted else "low",
            "evidence_refs": [row["evidence_id"] for row in adopted if row.get("evidence_id")],
            "caveats": [] if adopted else ["当前没有通过质量门的证据，不能给出确定结论。"],
        }

    def check_claim_decision(self, decision: dict[str, Any]) -> ContractCheck:
        if decision.get("evidence_refs"):
            return ContractCheck(status="pass", score=0.72)
        return ContractCheck(
            status="needs_revision",
            score=0.45,
            blocking_issues=["no_adopted_evidence"],
            revision_instructions=["继续查找可验证的官方、地图、平台或网页证据。"],
        )

    def compose_answer(self, decision: dict[str, Any], *, query: str) -> str:
        adopted_value = decision.get("adopted_value")
        evidence_refs = decision.get("evidence_refs") or []
        by_type = decision.get("by_source_type") or {}

        if not adopted_value and not evidence_refs:
            return (
                f"关于“{query}”，当前没有通过质量门的证据，不能给出确定结论。"
                f"建议尝试更具体的搜索词或查阅相关官方网站。"
            )

        lines = [f"关于“{query}”，根据当前可采纳证据整理如下："]

        for source_type, items in by_type.items():
            if not items:
                continue
            type_label = _SOURCE_TYPE_LABELS.get(source_type, source_type)
            for item in items[:2]:
                summary = (item.get("claim_summary") or "")[:200]
                if summary:
                    lines.append(f"- [{type_label}] {summary}")

        if not lines[1:]:
            lines.append(f"- {adopted_value[:300] if adopted_value else '当前无可采纳的硬证据。'}")

        caveats = decision.get("caveats") or []
        if caveats:
            lines.append("")
            for c in caveats[:3]:
                lines.append(f"注意：{c}")

        return "\n".join(lines)


_SOURCE_TYPE_LABELS: dict[str, str] = {
    "official": "官方来源",
    "ticket_platform": "票务平台",
    "map": "地图数据",
    "web": "网络参考",
    "context_seed": "背景知识",
    "review_platform": "评论参考",
}


def _claim_text(ev: EvidenceRecord) -> str:
    return " ".join(str(c.get("text") or c) for c in ev.claims if isinstance(c, dict)).strip()


def _reject(ev: EvidenceRecord, reason: str) -> dict[str, Any]:
    return {
        "evidence_id": ev.evidence_id,
        "source_name": ev.source_name,
        "claim_summary": _claim_text(ev),
        "rejection_reason": reason,
    }
