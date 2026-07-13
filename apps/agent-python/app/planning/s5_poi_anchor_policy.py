"""S5 task-class policy: mandatory POI anchor before retrieval (nearby-style tasks only)."""

from __future__ import annotations

from typing import Any

from app.evidence.poi_anchor_extraction import resolve_coordinates_from_evidence
from app.understanding.information_need_aliases import is_nearby_need
from app.understanding.intent_profile import PrimaryIntent
from app.understanding.semantic_frame_model import DecisionType, SemanticFrame
from app.understanding.travel_task import TravelTaskType

TravelAgentState = Any

# Task classes that require entity_resolution_agent before fact/keyword retrieval in S5.
_MANDATORY_POI_INTENTS = frozenset({PrimaryIntent.NEARBY})
_MANDATORY_POI_DECISIONS = frozenset({DecisionType.NEARBY_SEARCH})
_MANDATORY_POI_TRAVEL_TASKS = frozenset(
    {
        TravelTaskType.FOOD_NEARBY,
        TravelTaskType.LODGING_AREA,
    }
)

_SUBAGENTS_BLOCKED_UNTIL_POI = frozenset(
    {
        "fact_search_agent",
        "keyword_search_agent",
    }
)


def task_requires_mandatory_poi_anchor(state: TravelAgentState) -> bool:
    """True only for nearby-style task classes that need a geo anchor before POI retrieval."""
    profile = state.intent_profile
    if profile and profile.primary_intent in _MANDATORY_POI_INTENTS:
        return True

    frame = state.semantic_frame
    if frame and frame.decision_type in _MANDATORY_POI_DECISIONS:
        return True

    travel_task = state.travel_task
    if travel_task and travel_task.task_type in _MANDATORY_POI_TRAVEL_TASKS:
        return True

    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if req.priority == "required" and is_nearby_need(req.claim_type):
                return True

    return False


def _subagent_results(state: TravelAgentState) -> list[dict]:
    structured = state.structured_result or {}
    raw = structured.get("subagent_results") or []
    return [r for r in raw if isinstance(r, dict)]


def entity_resolution_attempted(state: TravelAgentState) -> bool:
    return any(r.get("subagent") == "entity_resolution_agent" for r in _subagent_results(state))


def poi_anchor_satisfied(state: TravelAgentState) -> bool:
    """POI gate cleared: entity subagent ran once, or anchored coordinates already in evidence."""
    if entity_resolution_attempted(state):
        return True
    return resolve_coordinates_from_evidence(
        list(state.evidence or []),
        structured_result=state.structured_result,
    ) is not None


def anchor_place_name(state: TravelAgentState) -> str | None:
    frame = state.semantic_frame
    if frame and frame.entities and frame.entities.places:
        return str(frame.entities.places[0]).strip() or None
    return None


def mandatory_poi_entity_required(state: TravelAgentState) -> bool:
    """S5 must delegate entity_resolution_agent before other retrieval subagents."""
    if not task_requires_mandatory_poi_anchor(state):
        return False
    if poi_anchor_satisfied(state):
        return False
    if not anchor_place_name(state):
        return False
    if entity_resolution_attempted(state):
        return False
    return True


def blocks_subagent_until_poi_anchor(state: TravelAgentState, subagent: str) -> bool:
    if not task_requires_mandatory_poi_anchor(state):
        return False
    if poi_anchor_satisfied(state):
        return False
    if subagent == "entity_resolution_agent":
        return False
    return subagent in _SUBAGENTS_BLOCKED_UNTIL_POI


def build_entity_resolution_arguments(state: TravelAgentState) -> dict:
    place = anchor_place_name(state) or ""
    frame: SemanticFrame | None = state.semantic_frame
    params: dict[str, str] = {}
    if frame and frame.entities:
        if frame.entities.city:
            params["city"] = frame.entities.city
        if frame.entities.region:
            params["region"] = frame.entities.region
    return {
        "lookup_intent": f"锚定用户所指地点：{place}",
        "claim_target": "entity_resolution",
        "search_query": place,
        "anchor_keywords": [place] if place else [],
        "information_need": "entity_resolution",
        "tool_parameters": params,
    }
