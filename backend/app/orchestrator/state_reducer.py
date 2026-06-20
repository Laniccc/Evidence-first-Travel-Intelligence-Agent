from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
from app.orchestrator.state_policy import StateNodePolicy
from app.orchestrator.trace import TraceRecorder
from app.schemas.final_answer_draft import FinalAnswerDraft
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.place_candidate import PlaceCandidate
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.user_query import TravelAgentState


_QUERY_UNDERSTANDING_FIELDS = frozenset(
    {"query_understanding", "travel_task", "semantic_frame", "rewritten_query_result", "next_state"}
)

_ANSWER_COMPOSITION_FIELDS = frozenset({"final_response", "structured_result"})


class StateReducer:
    """Safely merge action results into TravelAgentState — no arbitrary writes."""

    def apply(
        self,
        state: TravelAgentState,
        action: AgentAction,
        result: ActionResult,
        policy: StateNodePolicy,
    ) -> TravelAgentState:
        if not result.ok:
            state.limitations.append(result.error or f"{policy.state_name} action failed")
            return state

        if action.action_type == AgentActionType.CALL_SUBAGENT:
            state = self._apply_subagent_result(state, action.target or "", result.output, policy)
        elif action.action_type == AgentActionType.UPDATE_STATE:
            state = self._apply_whitelisted(state, result.output.get("updates", action.arguments), policy)
        elif action.action_type == AgentActionType.ASK_CLARIFICATION:
            state = self._apply_clarification(state, result.output)
        elif action.action_type == AgentActionType.CALL_TOOL:
            evidence = result.output.get("evidence", [])
            if evidence:
                state.evidence = list(state.evidence) + list(evidence)
        elif action.action_type == AgentActionType.FAIL_STATE:
            state.limitations.append(action.reason_summary or "state failed")
            state.next_state = "failed"

        return state

    def _apply_subagent_result(
        self,
        state: TravelAgentState,
        target: str,
        output: dict,
        policy: StateNodePolicy,
    ) -> TravelAgentState:
        if target == "query_understanding" and "query_understanding" in output:
            qu = output["query_understanding"]
            if isinstance(qu, QueryUnderstandingResult):
                state = self._apply_qu_result(state, qu)
            if policy.state_name == "query_understanding":
                TraceRecorder.add(state, f"✓ [loop] query_understanding 完成：{qu.rewritten_query[:72]}")
                if state.semantic_frame:
                    TraceRecorder.add(
                        state,
                        f"✓ [loop] SemanticFrame：{state.semantic_frame.query_scope.value}/"
                        f"{state.semantic_frame.decision_type.value}",
                    )
        elif target == "semantic_frame_builder" and "semantic_frame" in output:
            frame = output["semantic_frame"]
            if isinstance(frame, SemanticFrame):
                state.semantic_frame = frame
                if state.query_understanding:
                    state.query_understanding.semantic_frame = frame
        elif target == "place_entity_extractor" and "place_candidates" in output:
            candidates = output["place_candidates"]
            if state.semantic_frame and candidates:
                pois = [
                    c.canonical_name or c.mention
                    for c in candidates
                    if isinstance(c, PlaceCandidate) and c.is_poi
                ]
                city = next(
                    (c.city for c in candidates if isinstance(c, PlaceCandidate) and c.is_city and c.city),
                    None,
                )
                country = next(
                    (c.country for c in candidates if isinstance(c, PlaceCandidate) and c.country),
                    None,
                )
                if pois:
                    state.semantic_frame.entities.places = pois
                if city:
                    state.semantic_frame.entities.city = city
                if country:
                    state.semantic_frame.entities.country = country
        elif target == "composer_agent" and "result" in output:
            draft = output["result"]
            if isinstance(draft, FinalAnswerDraft):
                state = self._apply_composition_draft(state, draft)
            elif isinstance(draft, dict):
                state = self._apply_composition_draft(state, FinalAnswerDraft.model_validate(draft))
        elif target == "composer_agent" and "final_response" in output:
            state.final_response = output["final_response"]
            TraceRecorder.add(state, "✓ [loop] AnswerComposition 完成")
        return state

    def apply_finish(
        self,
        state: TravelAgentState,
        action: AgentAction,
        policy: StateNodePolicy,
    ) -> TravelAgentState:
        result = action.arguments.get("result")
        if policy.state_name == "query_understanding" and result is not None:
            qu = result if isinstance(result, QueryUnderstandingResult) else QueryUnderstandingResult.model_validate(result)
            state = self._apply_qu_result(state, qu)
            TraceRecorder.add(
                state,
                f"✓ [{policy.state_name}] FINISH_STATE → QueryUnderstandingResult",
            )
        elif policy.state_name == "answer_composition" and result is not None:
            draft = result if isinstance(result, FinalAnswerDraft) else FinalAnswerDraft.model_validate(result)
            state = self._apply_composition_draft(state, draft)
            TraceRecorder.add(
                state,
                f"✓ [{policy.state_name}] FINISH_STATE → FinalAnswerDraft",
            )
        elif action.arguments.get("final_response"):
            state.final_response = action.arguments["final_response"]
        return state

    def _apply_composition_draft(self, state: TravelAgentState, draft: FinalAnswerDraft) -> TravelAgentState:
        state.final_response = draft.render_text()
        structured = dict(state.structured_result or {})
        structured["final_answer_draft"] = draft.model_dump()
        state.structured_result = structured
        TraceRecorder.add(state, "✓ [loop] AnswerComposition 完成")
        return state

    def _apply_qu_result(self, state: TravelAgentState, result: QueryUnderstandingResult) -> TravelAgentState:
        state.query_understanding = result
        state.travel_task = result.travel_task
        state.semantic_frame = result.semantic_frame
        state.rewritten_query_result = RewrittenQueryResult(
            rewritten_query=result.rewritten_query,
            resolved_references=result.resolved_references,
            missing_critical_info=result.missing_critical_info,
            needs_clarification=result.needs_clarification,
            clarification_prompt=result.clarification_question,
            assumptions=result.assumptions,
            confidence=result.confidence,
            key_concerns=result.key_concerns,
        )
        return state

    def _apply_clarification(self, state: TravelAgentState, output: dict) -> TravelAgentState:
        state.next_state = "clarification_response"
        state.final_response = output.get("clarification_question") or "请补充关键信息。"
        missing = output.get("missing_critical_info", [])
        state.limitations.extend(missing)
        if state.query_understanding:
            state.query_understanding.needs_clarification = True
            state.query_understanding.clarification_question = state.final_response
        return state

    def _apply_whitelisted(
        self,
        state: TravelAgentState,
        updates: dict,
        policy: StateNodePolicy,
    ) -> TravelAgentState:
        allowed = self._allowed_fields(policy)
        for key, value in updates.items():
            if key not in allowed:
                state.limitations.append(f"Rejected unauthorized state update: {key}")
                continue
            setattr(state, key, value)
        return state

    @staticmethod
    def _allowed_fields(policy: StateNodePolicy) -> frozenset[str]:
        if policy.state_name == "query_understanding":
            return _QUERY_UNDERSTANDING_FIELDS
        if policy.state_name == "answer_composition":
            return _ANSWER_COMPOSITION_FIELDS
        return frozenset()
