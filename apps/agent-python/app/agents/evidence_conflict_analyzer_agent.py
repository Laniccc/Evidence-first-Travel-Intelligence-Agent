"""S7: detect conflicts and summarize for composition."""

from __future__ import annotations

import json
import logging

from app.agents.review_mining_agent import VerifierAgent
from app.llm_client import LLMClient
from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


class EvidenceConflictAnalyzerAgent:
    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client or LLMClient()

    async def run(self, state: TravelAgentState, arguments: dict | None = None) -> dict:
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        conflicts = VerifierAgent.detect_conflicts(evidence)
        notes = [c.get("description", str(c)) for c in conflicts]

        if self.llm._should_use_anthropic() and (conflicts or evidence):
            try:
                llm_notes = await self._llm_summarize(state, conflicts)
                if llm_notes:
                    notes = llm_notes
            except Exception as exc:
                logger.warning("EvidenceConflictAnalyzer LLM failed: %s", exc)

        return {"conflict_notes": notes, "conflict_analyzed": True}

    async def _llm_summarize(self, state: TravelAgentState, conflicts: list[dict]) -> list[str] | None:
        structured = state.structured_result or {}
        curated = structured.get("curated_claims") or []
        system = (
            "Summarize evidence conflicts for travel answer composition. Return ONLY JSON:\n"
            '{"conflict_notes":["..."]}\n'
            "Do not invent conflicts; only describe provided conflict records."
        )
        payload = {
            "conflicts": conflicts,
            "curated_claims": curated[:12],
            "user_need_residual": state.user_need_residual.model_dump() if state.user_need_residual else {},
        }
        raw = await self.llm.complete(system=system, user=json.dumps(payload, ensure_ascii=False), max_tokens=400)
        data = json.loads(raw.strip())
        if isinstance(data, dict) and isinstance(data.get("conflict_notes"), list):
            return [str(n) for n in data["conflict_notes"]]
        return None
