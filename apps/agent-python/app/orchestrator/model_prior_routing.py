"""Route MODEL_PRIOR_ALLOWED through S5 (evidence planning) before composition."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
_APPLIED = False


def apply_model_prior_s5_routing() -> None:
    """Seed user_goal / information_needs so MODEL_PRIOR_ALLOWED enters S5 tool loop."""
    global _APPLIED
    if _APPLIED:
        return

    try:
        from app.orchestrator.state_machine import TravelAgentStateMachine
    except ImportError:
        logger.debug("state_machine not loaded; skip MODEL_PRIOR S5 routing patch")
        return

    original_advisory = TravelAgentStateMachine._run_advisory

    async def patched_advisory(self, state):
        from app.agents.information_need_planner import InformationNeedPlanner
        from app.orchestrator.trace import TraceRecorder
        from app.schemas.user_query import UserGoal

        if state.travel_task and not state.information_needs:
            state.information_needs = InformationNeedPlanner.plan(state.travel_task)

        if not state.user_goal:
            frame = state.semantic_frame
            task = state.travel_task
            country = (frame.entities.country if frame else None) or (task.country if task else None)
            city = (frame.entities.city if frame else None) or (task.city if task else None)
            if country or city:
                state.user_goal = UserGoal(destination_country=country, destination_city=city)
                TraceRecorder.add(
                    state,
                    "✓ MODEL_PRIOR_ALLOWED → 进入 S5 工具规划（非直接 KnowledgePrior）",
                )

        return await original_advisory(self, state)

    TravelAgentStateMachine._run_advisory = patched_advisory
    _APPLIED = True
    logger.info("MODEL_PRIOR_ALLOWED S5 routing patch applied")
