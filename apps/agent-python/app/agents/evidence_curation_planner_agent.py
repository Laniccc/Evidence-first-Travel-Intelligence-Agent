"""S7: plan evidence curation steps from user needs + evidence index."""

from __future__ import annotations

import json
import logging

from app.llm_client import LLMClient
from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


class EvidenceCurationPlannerAgent:
    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client or LLMClient()

    async def run(self, state: TravelAgentState, arguments: dict | None = None) -> dict:
        residual = state.user_need_residual
        needs = [n.need_type for n in residual.information_needs] if residual else []
        if not needs and state.semantic_frame:
            needs = list(state.semantic_frame.information_needs)
        if not needs and state.response_contract:
            needs = [c.claim_type for c in state.response_contract.claim_requirements]

        index = self._evidence_index(state.evidence)
        if self.llm._should_use_anthropic() and index:
            try:
                plan = await self._llm_plan(state, needs, index)
                if plan:
                    return {"curation_plan": plan}
            except Exception as exc:
                logger.warning("EvidenceCurationPlanner LLM failed: %s", exc)

        return {
            "curation_plan": {
                "needs_to_filter": needs or ["general"],
                "run_conflict_analysis": len(state.evidence) > 1,
                "rationale": "Rule-based curation plan",
            }
        }

    @staticmethod
    def _evidence_index(evidence: list) -> list[dict]:
        rows: list[dict] = []
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            claim_types = [c.claim_type.value for c in ev.claims]
            rows.append(
                {
                    "evidence_id": ev.evidence_id,
                    "source_name": ev.source_name,
                    "place_name": ev.place_name,
                    "confidence": ev.confidence,
                    "claim_types": claim_types,
                }
            )
        return rows

    async def _llm_plan(self, state: TravelAgentState, needs: list[str], index: list[dict]) -> dict | None:
        system = (
            "Plan evidence curation for travel Q&A. Return ONLY JSON:\n"
            '{"needs_to_filter":["..."], "run_conflict_analysis": true, "rationale":"..."}\n'
            "Use user_need_residual for needs — do not treat user text as verified facts."
        )
        payload = {
            "user_need_residual": state.user_need_residual.model_dump() if state.user_need_residual else {},
            "evidence_index": index,
            "needs_hint": needs,
        }
        raw = await self.llm.complete(system=system, user=json.dumps(payload, ensure_ascii=False), max_tokens=400)
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if isinstance(data, dict) and data.get("needs_to_filter"):
            return data
        return None
