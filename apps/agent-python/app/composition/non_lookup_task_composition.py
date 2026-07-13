"""S8 presentation and draft shaping for non-lookup travel tasks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from app.composition.final_answer_draft import FinalAnswerDraft, FinalAnswerSection


_PRESENTATION_REVIEW_CLAIMS = {
    "review_summary",
    "review_aspect",
    "value_for_money",
    "crowd_risk",
    "queue_risk",
    "commercialization_risk",
    "family_friendly",
    "elderly_suitability",
}
_PRESENTATION_LIVE_CLAIMS = {
    "current_weather",
    "weather",
    "weather_today",
    "traffic_status",
    "congestion_risk",
    "current_crowd",
    "current_crowd_estimate",
    "queue_time",
    "temporary_closure",
}
_PRESENTATION_HARD_FACT_CLAIMS = {
    "ticket_price",
    "opening_hours",
    "temporary_closure",
    "reservation_policy",
    "seasonal_operation_status",
}
_PRESENTATION_ROUTE_CLAIMS = {
    "route_plan",
    "duration",
    "distance",
    "route_steps",
    "traffic_status",
}


def build_minimal_clarification_question(
    *,
    related_poi: bool,
    ambiguous_candidate_labels: Iterable[str],
    missing_slots: Iterable[str],
) -> str:
    """Present the smallest useful question from already-resolved ambiguity inputs."""
    if related_poi:
        return (
            "Do you want recommendations ranked within the same scenic area, "
            "or a specific entrance/service point?"
        )
    labels = [str(label).strip() for label in ambiguous_candidate_labels if str(label).strip()]
    if labels:
        return "Which place do you mean: " + " / ".join(labels[:3]) + "?"
    slots = [str(slot).strip() for slot in missing_slots if str(slot).strip()]
    if slots:
        return f"Please clarify {slots[0]}."
    return "Which exact place or city do you mean?"


def build_non_lookup_task_draft(
    *,
    profile_payload: Mapping[str, Any],
    target_label: str,
    report: Any | None,
    evidence: Iterable[Any],
    user_visible_limitations: Iterable[str],
    clarification_question: str,
    nearby_candidates: Iterable[Any],
) -> FinalAnswerDraft:
    """Shape an evidence-evaluation result into a presentation-only answer draft."""
    task_class = str(profile_payload.get("task_class") or "advisory")
    compose_mode = str(profile_payload.get("compose_mode") or "advisory")
    cited = _adopted_evidence_ids(report)
    values = _adopted_values_by_claim(evidence, cited)
    limitations = _dedupe([*user_visible_limitations, *_decision_limitations(report)])

    if task_class == "review_check":
        bullets = _claim_bullets(values, _PRESENTATION_REVIEW_CLAIMS) or [
            "No adoptable review signal was found."
        ]
        return FinalAnswerDraft(
            headline=f"{target_label} review tendency",
            conclusion=_conclusion_from_report(report, fallback="Review signal is limited."),
            sections=[FinalAnswerSection(title="Review tendency", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=compose_mode,
        )
    if task_class == "planning":
        return FinalAnswerDraft(
            headline=f"{target_label} itinerary feasibility",
            conclusion=_conclusion_from_report(
                report,
                fallback="Feasibility depends on missing route evidence.",
            ),
            sections=[FinalAnswerSection(title="Time blocks", bullets=_time_block_bullets(values))],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=compose_mode,
        )
    if task_class == "comparison":
        return FinalAnswerDraft(
            headline=f"{target_label} comparison",
            conclusion=_conclusion_from_report(
                report,
                fallback="Only aligned evidence should drive the comparison.",
            ),
            sections=[
                FinalAnswerSection(
                    title="Aligned dimensions",
                    bullets=_aligned_dimension_bullets(report),
                ),
                FinalAnswerSection(
                    title="Evidence asymmetry",
                    bullets=_asymmetry_bullets(report),
                ),
            ],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=compose_mode,
        )
    if task_class == "nearby":
        bullets = [
            f"{candidate.name}: {candidate.distance_m or 'unknown'}m; {candidate.reason}"
            for candidate in nearby_candidates
            if getattr(candidate, "accepted", False)
        ] or ["No nearby candidate passed category and distance filters."]
        return FinalAnswerDraft(
            headline=f"{target_label} nearby recommendations",
            conclusion="Nearby candidates are listed only when map/category evidence supports them.",
            sections=[FinalAnswerSection(title="Distance and reason", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=compose_mode,
        )
    if task_class == "realtime_check":
        bullets = _claim_bullets(values, _PRESENTATION_LIVE_CLAIMS) or [
            "No fresh live evidence was adopted."
        ]
        return FinalAnswerDraft(
            headline=f"{target_label} realtime check",
            conclusion=_conclusion_from_report(
                report,
                fallback="Realtime status cannot be confirmed without fresh evidence.",
            ),
            sections=[FinalAnswerSection(title="Freshness note", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=compose_mode,
        )
    if task_class == "clarification":
        return FinalAnswerDraft(
            headline="Need one clarification",
            conclusion=clarification_question,
            sections=[FinalAnswerSection(title="Question", bullets=[clarification_question])],
            limitations=[],
            cited_evidence_ids=[],
            compose_mode=compose_mode,
        )

    suitable = _claim_bullets(
        values,
        {"review_summary", "seasonality", "route_plan", "weather"},
    )
    hard = _claim_bullets(
        values,
        _PRESENTATION_HARD_FACT_CLAIMS | _PRESENTATION_LIVE_CLAIMS,
    )
    return FinalAnswerDraft(
        headline=f"{target_label} advisory",
        conclusion=_conclusion_from_report(
            report,
            fallback="Recommendation must stay bounded by available evidence.",
        ),
        sections=[
            FinalAnswerSection(
                title="Suitable for",
                bullets=suitable or ["Evidence is not strong enough for a firm fit statement."],
            ),
            FinalAnswerSection(
                title="Not suitable for",
                bullets=hard or ["No hard/live blocker was adopted from evidence."],
            ),
        ],
        limitations=limitations,
        cited_evidence_ids=cited,
        compose_mode=compose_mode,
    )


def prepare_non_lookup_task_compose_context(
    *,
    compose_kwargs: Mapping[str, Any],
    profile_payload: Mapping[str, Any],
    trace_payload: Mapping[str, Any],
    draft: FinalAnswerDraft,
    target_label: str,
) -> dict[str, Any]:
    """Build the S8 prompt context from explicitly supplied profile and evidence outputs."""
    return {
        **dict(compose_kwargs),
        "compose_mode": profile_payload.get("compose_mode") or "advisory",
        "target_label": compose_kwargs.get("target_label") or target_label,
        "non_lookup_task_profile": dict(profile_payload),
        "non_lookup_task_trace": dict(trace_payload),
        "task_adoption_summary": dict(trace_payload.get("adoption_levels") or {}),
        "task_composer_draft": draft.model_dump(mode="json"),
    }


def _adopted_evidence_ids(report: Any | None) -> list[str]:
    if not report:
        return []
    evidence_ids: list[str] = []
    for decision in getattr(report, "claim_decisions", []) or []:
        if getattr(decision, "adoption", None) in {
            "adopt",
            "adopt_with_limitation",
            "candidate_only",
        }:
            evidence_ids.extend(getattr(decision, "adopted_evidence_ids", []) or [])
    return _dedupe(evidence_ids)


def _adopted_values_by_claim(
    evidence: Iterable[Any],
    evidence_ids: Iterable[str],
) -> dict[str, list[str]]:
    allowed = set(evidence_ids)
    values: dict[str, list[str]] = defaultdict(list)
    for item in evidence or []:
        if allowed and getattr(item, "evidence_id", None) not in allowed:
            continue
        for claim in getattr(item, "claims", []) or []:
            claim_type = _claim_type_value(getattr(claim, "claim_type", ""))
            value = str(getattr(claim, "value", "")).strip()
            if value:
                values[claim_type].append(value)
    return dict(values)


def _claim_bullets(values: Mapping[str, list[str]], claim_types: Iterable[str]) -> list[str]:
    bullets: list[str] = []
    for claim_type in claim_types:
        for value in values.get(claim_type, [])[:2]:
            bullets.append(f"{claim_type}: {value}")
    return bullets[:6]


def _decision_limitations(report: Any | None) -> list[str]:
    if not report:
        return []
    limitations: list[str] = []
    for decision in getattr(report, "claim_decisions", []) or []:
        limitations.extend(getattr(decision, "user_visible_limitations", []) or [])
        limitations.extend(getattr(decision, "limitations", []) or [])
    return _dedupe(limitations)


def _conclusion_from_report(report: Any | None, *, fallback: str) -> str:
    decisions = list(getattr(report, "claim_decisions", []) or []) if report else []
    if not decisions:
        return fallback
    adopted = [
        str(getattr(decision, "claim_type", ""))
        for decision in decisions
        if getattr(decision, "adoption", None)
        in {"adopt", "adopt_with_limitation", "candidate_only"}
    ]
    refused = [
        str(getattr(decision, "claim_type", ""))
        for decision in decisions
        if getattr(decision, "adoption", None) in {"refuse_to_guess", "ask_clarification"}
    ]
    if adopted:
        tail = f"; limited on {', '.join(refused[:3])}" if refused else ""
        return f"Adopted evidence for {', '.join(adopted[:4])}{tail}."
    return fallback


def _time_block_bullets(values: Mapping[str, list[str]]) -> list[str]:
    bullets = _claim_bullets(values, _PRESENTATION_ROUTE_CLAIMS | {"opening_hours"})
    return bullets or [
        "Do not build a detailed timetable until route duration and opening-hours evidence exist."
    ]


def _aligned_dimension_bullets(report: Any | None) -> list[str]:
    if not report:
        return ["No comparison dimensions evaluated."]
    bullets = [
        f"{decision.claim_type}: {decision.coverage_quality}/{decision.adoption}"
        for decision in getattr(report, "claim_decisions", []) or []
        if "evidence_asymmetry" not in str(getattr(decision, "reason", ""))
    ]
    return bullets or ["No aligned dimension is strong enough for a direct comparison."]


def _asymmetry_bullets(report: Any | None) -> list[str]:
    if not report:
        return ["Evidence asymmetry was not evaluated."]
    bullets = [
        f"{decision.claim_type}: {', '.join(getattr(decision, 'user_visible_limitations', []) or []) or decision.reason}"
        for decision in getattr(report, "claim_decisions", []) or []
        if "evidence_asymmetry" in str(getattr(decision, "reason", ""))
        or getattr(decision, "user_visible_limitations", [])
    ]
    return bullets or ["No evidence asymmetry detected in evaluated dimensions."]


def _claim_type_value(claim_type: Any) -> str:
    return str(getattr(claim_type, "value", claim_type))


def _dedupe(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(values))
