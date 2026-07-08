"""Experimental Root Agent / Supervisor for the new Agent Core architecture."""

from __future__ import annotations

from app.orchestrator.agent_core_control_tools import AgentCoreControlTools
from app.orchestrator.agent_core_pipeline_gate import PipelineGate, ToolVisibility
from app.orchestrator.agent_core_research_plan import build_research_plan
from app.orchestrator.agent_core_store import ensure_agent_core_store
from app.orchestrator.agent_core_tool_surface import PhaseToolSurface, RunEnvelope
from app.schemas.response import TravelQueryResponse


class RootAgentSupervisor:
    """Owns phase progression and delegates execution to the Tool Surface."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.surface = PhaseToolSurface(runtime)
        self.gate = PipelineGate(runtime.capability_registry, runtime.tools)
        self.controls = AgentCoreControlTools()

    async def run(
        self,
        *,
        query: str,
        user_context: dict | None,
        session_id: str | None,
    ) -> TravelQueryResponse:
        self.runtime.tools.clear_traces()
        ctx, memory, state = self.runtime._build_conversation_context(query, user_context, session_id)
        envelope = RunEnvelope(
            query=query,
            user_context=user_context,
            session_id=session_id,
            ctx=ctx,
            memory=memory,
            state=state,
        )
        self._record_visibility(envelope, "input_contract")
        maybe_state = await self.surface.build_input_contract(envelope)
        if isinstance(maybe_state, TravelQueryResponse):
            return maybe_state
        if self.surface.requires_clarification(envelope):
            return self.surface.clarification_response(envelope)

        self._record_visibility(envelope, "pipeline_gate")
        maybe_state = await self.surface.apply_region_policy(envelope)
        if isinstance(maybe_state, TravelQueryResponse):
            return maybe_state

        research_visibility = self._record_visibility(envelope, "research_plan")
        self._record_research_plan(envelope, research_visibility)

        self._record_visibility(envelope, "evidence_acquisition")
        await self.surface.run_evidence_acquisition_and_review(envelope)

        self._record_visibility(envelope, "answer_draft")
        await self.surface.compose_answer_draft(envelope)

        self._record_visibility(envelope, "citation_guard")
        confidence = self.surface.run_citation_guard(envelope)

        self._record_visibility(envelope, "delivery")
        return self.surface.deliver(envelope, confidence)

    def _record_visibility(self, envelope: RunEnvelope, phase: str) -> ToolVisibility:
        visibility = self.gate.visible_tools(envelope.state, phase=phase)
        store = ensure_agent_core_store(envelope.state)
        store.add_phase_output(
            phase,
            kind="tool_visibility",
            status="succeeded",
            payload=visibility.model_dump(mode="json", exclude={"projection"}),
        )
        return visibility

    def _record_research_plan(self, envelope: RunEnvelope, visibility: ToolVisibility) -> None:
        plan = build_research_plan(envelope.state, visibility=visibility)
        payload = plan.model_dump(mode="json")
        store = ensure_agent_core_store(envelope.state)
        artifact = store.add_artifact(
            artifact_type="research_plan",
            status="pending_review",
            payload=payload,
        )
        output = store.add_phase_output(
            "research_plan",
            kind="research_plan",
            status="pending_review",
            payload={"artifact_id": artifact.id, **payload},
            created_by="root_agent",
        )
        self.controls.approve_phase(
            envelope.state,
            phase="research_plan",
            output_id=output.id,
            approved_by="root_agent:auto",
        )
