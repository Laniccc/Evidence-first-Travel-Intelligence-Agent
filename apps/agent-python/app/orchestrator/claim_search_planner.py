"""S5 search planning helpers — search keywords come from LLM sub-agents only."""

from __future__ import annotations

import re

from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState

_NO_HITS = re.compile(r"No search hits|无结果|returned no results", re.I)


def is_search_miss_value(value: str) -> bool:
    """True when a claim value is a search/tool miss sentinel, not substantive content."""
    return bool(_NO_HITS.search(str(value)))


class ClaimSearchPlanner:
    """Utilities for S5 search loop limits and LLM planner context."""

    @classmethod
    def max_search_attempts(cls, state: TravelAgentState) -> int:
        contract = state.response_contract
        if contract and any(
            c.priority == "required" and not c.model_prior_allowed
            for c in contract.claim_requirements
        ):
            return 6
        return 3

    @classmethod
    def primary_information_need(cls, state: TravelAgentState) -> str | None:
        contract = state.response_contract
        if contract:
            for claim in contract.claim_requirements:
                if claim.priority == "required":
                    return claim.claim_type
            if contract.claim_requirements:
                return contract.claim_requirements[0].claim_type
        frame = state.semantic_frame
        if frame and frame.information_needs:
            return frame.information_needs[0]
        return None

    @classmethod
    def planning_context(cls, state: TravelAgentState) -> dict:
        """Structured context passed to SearchTaskPlannerAgent LLM."""
        frame = state.semantic_frame
        contract = state.response_contract
        claim_types: list[str] = []
        if contract:
            claim_types = [c.claim_type for c in contract.claim_requirements]
        elif frame and frame.information_needs:
            claim_types = list(frame.information_needs)

        entities = {}
        if frame and frame.entities:
            entities = {
                "country": frame.entities.country,
                "region": frame.entities.region,
                "city": frame.entities.city,
                "places": list(frame.entities.places or []),
            }

        tried = sorted(cls.tried_from_traces(state))
        structured = state.structured_result or {}
        completed_ids = structured.get("completed_search_task_ids") or []

        return {
            "raw_query": state.raw_user_query,
            "normalized_request": frame.normalized_request if frame else None,
            "decision_type": frame.decision_type.value if frame and frame.decision_type else None,
            "task_family": frame.task_family.value if frame and frame.task_family else None,
            "entities": entities,
            "claim_types": claim_types,
            "primary_information_need": cls.primary_information_need(state),
            "tried_search_queries": tried,
            "completed_search_task_ids": completed_ids,
            "failed_snippets": cls.failed_snippets(state),
            "max_tasks": cls.max_search_attempts(state),
            "response_contract_summary": contract.user_goal_summary if contract else None,
        }

    @staticmethod
    def dedupe(items) -> list[str]:
        return list(dict.fromkeys(str(x).strip() for x in items if x and str(x).strip()))

    @staticmethod
    def tried_from_traces(state: TravelAgentState) -> set[str]:
        tried: set[str] = set()
        for trace in state.tool_traces:
            if trace.tool_name != "search_mcp":
                continue
            q = (trace.input or {}).get("query")
            if q:
                tried.add(str(q).strip())
        return tried

    @staticmethod
    def failed_snippets(state: TravelAgentState) -> list[str]:
        snippets: list[str] = []
        for ev in state.evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                value = str(claim.value)
                if _NO_HITS.search(value):
                    snippets.append(value[:160])
        return snippets[:8]

    @staticmethod
    def searches_failed(state: TravelAgentState) -> bool:
        return bool(ClaimSearchPlanner.failed_snippets(state))

    @staticmethod
    def search_call_count(state: TravelAgentState) -> int:
        return sum(1 for t in state.tool_traces if t.tool_name == "search_mcp")
