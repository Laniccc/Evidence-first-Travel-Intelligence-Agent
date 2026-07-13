"""S5 sub-agent: decide precise vs fuzzy nearby anchor before map/crawler retrieval."""

from __future__ import annotations

import importlib
import uuid
from typing import Any

from app.understanding.information_need_aliases import primary_nearby_need_from_state


def _module(name: str):
    return importlib.import_module(name)


class NearbyAnchorStrategyAgent:
    """
    High-priority nearby preflight: resolves whether to search per disambiguation
    candidate, at a gate, or with a fuzzy radius. Callable recursively from other sub-agents.
    """

    async def run(
        self,
        state: Any,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        extract_place_candidates = _module(
            "app.orchestration.place_disambiguation"
        ).extract_place_candidates
        build_nearby_search_targets = _module(
            "app.planning.nearby_anchor_policy"
        ).build_nearby_search_targets

        nearby_claim = str(
            arguments.get("nearby_claim")
            or arguments.get("claim_target")
            or arguments.get("information_need")
            or primary_nearby_need_from_state(state)
        )
        candidates = arguments.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            candidates = extract_place_candidates(list(state.evidence or []))
        if arguments.get("extra_candidates"):
            for item in arguments["extra_candidates"]:
                if isinstance(item, dict) and item not in candidates:
                    candidates.append(item)

        strategy = build_nearby_search_targets(
            state,
            [c for c in candidates if isinstance(c, dict)],
            nearby_claim=nearby_claim,
            evidence_list=arguments.get("evidence_list"),
        )
        structured = dict(state.structured_result or {})
        structured["nearby_anchor_strategy"] = strategy
        state.structured_result = structured

        return {
            "subagent": "nearby_anchor_strategy_agent",
            "task_id": arguments.get("task_id") or f"nearby-anchor-{uuid.uuid4().hex[:8]}",
            "parent_subagent": arguments.get("parent_subagent"),
            "nearby_claim": nearby_claim,
            **strategy,
            "evidence": [],
            "tool_traces": [],
            "tool_call_count": 0,
        }
