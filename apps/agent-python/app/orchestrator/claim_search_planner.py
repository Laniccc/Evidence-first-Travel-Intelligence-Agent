"""S5 search planning helpers — search keywords come from LLM sub-agents only."""

from __future__ import annotations

import re

from app.orchestrator.comparison_helpers import (
    active_place_name,
    comparison_search_anchors,
    disambiguated_place_label,
    is_comparison_mode,
)
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
        from app.config import get_settings

        cap = int(get_settings().mcp_max_tool_calls_per_state)
        contract = state.response_contract
        if contract and any(
            c.priority == "required" and not c.model_prior_allowed
            for c in contract.claim_requirements
        ):
            return min(cap, 4)
        return min(cap, 6)

    @classmethod
    def keyword_search_call_count(cls, state: TravelAgentState) -> int:
        structured = state.structured_result or {}
        completed = structured.get("completed_search_task_ids") or []
        return len(completed) if isinstance(completed, list) else 0

    @classmethod
    def _anchor_keywords(cls, state: TravelAgentState) -> list[str]:
        contract = state.response_contract
        if contract and contract.gated_search_keywords:
            return cls.dedupe(list(contract.gated_search_keywords))

        frame = state.semantic_frame
        keywords: list[str] = []
        if frame and frame.entities:
            keywords.extend(frame.entities.places or [])
            if frame.entities.city:
                keywords.append(frame.entities.city)
            if frame.entities.region:
                keywords.append(frame.entities.region)
        residual = state.user_need_residual
        if residual and residual.information_needs:
            keywords.extend(n.need_type for n in residual.information_needs)
        return cls.dedupe(keywords)

    @classmethod
    def evidence_highlights(cls, state: TravelAgentState) -> list[dict]:
        from app.schemas.evidence import ClaimType, Evidence

        rows: list[dict] = []
        for ev in state.evidence:
            if not isinstance(ev, Evidence):
                continue
            claims = []
            for claim in ev.claims[:6]:
                ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
                claims.append({"type": ct, "value": str(claim.value)[:160]})
            rows.append(
                {
                    "source_name": ev.source_name,
                    "place_name": ev.place_name,
                    "claims": claims,
                }
            )
        return rows[:15]

    @classmethod
    def recent_keyword_search_results(cls, state: TravelAgentState) -> list[dict]:
        structured = state.structured_result or {}
        bucket = structured.get("keyword_search_results") or []
        return bucket[-4:] if isinstance(bucket, list) else []

    @classmethod
    def search_hits_from_evidence(cls, state: TravelAgentState) -> list[dict]:
        from tools.official_source.url_normalizer import hits_from_evidence_list

        return hits_from_evidence_list(list(state.evidence))

    @classmethod
    def primary_information_need(cls, state: TravelAgentState) -> str | None:
        residual = state.user_need_residual
        if residual:
            for claim in residual.claim_requirements:
                if claim.priority == "required":
                    return claim.claim_type
            for need in residual.information_needs:
                if need.priority == "required":
                    return need.need_type
            if residual.claim_requirements:
                return residual.claim_requirements[0].claim_type
            if residual.information_needs:
                return residual.information_needs[0].need_type
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
            active = active_place_name(state) if is_comparison_mode(state) else None
            place_list = [active] if active else list(frame.entities.places or [])
            entities = {
                "country": frame.entities.country,
                "region": frame.entities.region,
                "city": frame.entities.city,
                "places": place_list,
            }

        tried = sorted(cls.tried_from_traces(state))
        structured = state.structured_result or {}
        completed_ids = structured.get("completed_search_task_ids") or []

        from app.orchestrator.official_source_search_templates import (
            OFFICIAL_SEARCH_QUERY_TEMPLATES,
            templates_for_claim,
        )
        from app.orchestrator.place_disambiguation_guard import extract_place_candidates

        place_candidates = extract_place_candidates(list(state.evidence))
        place = (entities.get("places") or [None])[0] if entities else None
        city = entities.get("city") if entities else None
        region = entities.get("region") if entities else None
        primary = cls.primary_information_need(state)

        anchor_keywords = cls._anchor_keywords(state)
        if is_comparison_mode(state) and place:
            anchor_keywords = comparison_search_anchors(place, frame, peer_places=state.comparison_peer_places)

        return {
            "raw_query": state.raw_user_query,
            "normalized_request": frame.normalized_request if frame else None,
            "decision_type": frame.decision_type.value if frame and frame.decision_type else None,
            "task_family": frame.task_family.value if frame and frame.task_family else None,
            "entities": entities,
            "anchor_keywords": anchor_keywords,
            "comparison_mode": is_comparison_mode(state),
            "comparison_active_place": active_place_name(state),
            "comparison_peer_places": list(state.comparison_peer_places or []),
            "disambiguated_place_label": (
                disambiguated_place_label(place, city=city, region=region)
                if place
                else None
            ),
            "claim_types": claim_types,
            "primary_information_need": cls.primary_information_need(state),
            "search_purpose_hint": cls.primary_information_need(state),
            "tried_search_queries": tried,
            "completed_search_task_ids": completed_ids,
            "keyword_search_count": cls.keyword_search_call_count(state),
            "max_keyword_searches": cls.max_search_attempts(state),
            "failed_snippets": cls.failed_snippets(state),
            "place_candidates": place_candidates,
            "evidence_highlights": cls.evidence_highlights(state),
            "recent_keyword_search_results": cls.recent_keyword_search_results(state),
            "user_need_residual": (
                state.user_need_residual.model_dump() if state.user_need_residual else None
            ),
            "agent_tool_definitions": (
                (state.structured_result or {}).get("_agent_tool_definitions")
                or []
            ),
            "response_contract_summary": contract.user_goal_summary if contract else None,
            "gated_search_keywords": (
                list(contract.gated_search_keywords)
                if contract and contract.gated_search_keywords
                else cls._anchor_keywords(state)
            ),
            "place_ambiguity": (
                contract.place_ambiguity_context.model_dump()
                if contract and contract.place_ambiguity_context
                else (
                    frame.place_ambiguity.model_dump()
                    if frame and frame.place_ambiguity
                    else None
                )
            ),
            "labeled_entities": (
                list(frame.labeled_entities)
                if frame and frame.labeled_entities
                else None
            ),
            "official_search_query_templates": OFFICIAL_SEARCH_QUERY_TEMPLATES,
            "official_search_queries_for_primary_need": templates_for_claim(
                primary, place_name=place or "", city=city or ""
            ),
        }

    @staticmethod
    def dedupe(items) -> list[str]:
        return list(dict.fromkeys(str(x).strip() for x in items if x and str(x).strip()))

    @staticmethod
    def tried_from_traces(state: TravelAgentState) -> set[str]:
        tried: set[str] = set()
        for trace in state.tool_traces:
            q = (trace.input or {}).get("query")
            if q:
                tried.add(str(q).strip())
        structured = state.structured_result or {}
        for item in structured.get("keyword_search_results") or []:
            if isinstance(item, dict) and item.get("search_query"):
                tried.add(str(item["search_query"]).strip())
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
