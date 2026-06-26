from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
from app.orchestrator.evidence_brief_builder import apply_evidence_brief
from app.orchestrator.state_policy import StateNodePolicy
from app.orchestrator.subagent_evidence_gate import filter_subagent_evidence
from app.orchestrator.trace import TraceRecorder
from app.schemas.evidence_brief import EvidenceBrief
from app.schemas.final_answer_draft import FinalAnswerDraft
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.place_candidate import PlaceCandidate
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.information_need import InformationNeed
from app.schemas.tool_trace import ToolTrace
from app.schemas.user_query import TravelAgentState
from app.tools.tool_router import ToolExecutionPlan


_QUERY_UNDERSTANDING_FIELDS = frozenset(
    {"query_understanding", "travel_task", "semantic_frame", "rewritten_query_result", "next_state"}
)

_ANSWER_COMPOSITION_FIELDS = frozenset({"final_response", "structured_result"})

_EVIDENCE_PLANNING_FIELDS = frozenset(
    {"information_needs", "tool_execution_plan", "limitations", "planning_notes"}
)


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
            state = self._apply_tool_result(state, action, result, policy)
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
        elif target == "search_task_planner_agent" and "search_tasks" in output:
            structured = dict(state.structured_result or {})
            new_tasks = output["search_tasks"]
            if output.get("refine"):
                existing = list(structured.get("search_tasks") or [])
                structured["search_tasks"] = existing + list(new_tasks)
            else:
                structured["search_tasks"] = new_tasks
            structured.setdefault("completed_search_task_ids", [])
            state.structured_result = structured
            TraceRecorder.add(
                state,
                f"✓ [A2A] search_task_planner → {output.get('task_count', len(output['search_tasks']))} keyword tasks",
            )
        elif target == "evidence_contradiction_decomposer_agent":
            structured = dict(state.structured_result or {})
            decomps = output.get("decompositions") or []
            structured["fact_decomposition"] = decomps
            if output.get("presentation_guidance"):
                structured["contradiction_presentation_guidance"] = output["presentation_guidance"]
            structured["_decompose_evidence_count"] = len(state.evidence)
            target_need = str(output.get("target_need") or "").strip()
            if target_need:
                done = list(structured.get("_decomposed_needs") or [])
                if target_need not in done:
                    done.append(target_need)
                structured["_decomposed_needs"] = done
            follow_up = output.get("follow_up_search_tasks") or []
            if follow_up:
                existing = list(structured.get("search_tasks") or [])
                structured["search_tasks"] = existing + list(follow_up)
            state.structured_result = structured
            item_count = sum(len(d.get("items") or []) for d in decomps if isinstance(d, dict))
            TraceRecorder.add(
                state,
                f"✓ [A2A] evidence_contradiction_decomposer → {item_count} decomposed fact tiers",
            )
        elif target in {
            "keyword_search_agent",
            "entity_resolution_agent",
            "route_feasibility_agent",
            "fact_search_agent",
            "fact_lookup_agent",
            "weather_context_agent",
        }:
            raw_evidence = output.get("evidence", [])
            accepted, rejected = filter_subagent_evidence(
                state,
                raw_evidence,
                subagent=target,
                output=output if isinstance(output, dict) else {},
            )
            if rejected:
                structured = dict(state.structured_result or {})
                gate_log = list(structured.get("subagent_evidence_gate_rejects") or [])
                gate_log.append(
                    {
                        "subagent": target,
                        "task_id": output.get("task_id"),
                        "rejected": rejected,
                    }
                )
                structured["subagent_evidence_gate_rejects"] = gate_log[-24:]
                state.structured_result = structured
                TraceRecorder.add(
                    state,
                    f"⊘ NEARBY evidence gate dropped {len(rejected)} item(s) from {target}",
                )
            evidence = accepted
            if evidence:
                state.evidence = list(state.evidence) + list(evidence)
            for item in output.get("tool_traces", []):
                if isinstance(item, ToolTrace):
                    state.tool_traces.append(item)
                elif isinstance(item, dict):
                    state.tool_traces.append(ToolTrace.model_validate(item))
            structured = dict(state.structured_result or {})
            completed = list(structured.get("completed_search_task_ids", []))
            task_id = output.get("task_id")
            if task_id and task_id not in completed:
                completed.append(task_id)
            structured["completed_search_task_ids"] = completed
            history = list(structured.get("keyword_search_results") or [])
            history.append(
                {
                    "task_id": task_id,
                    "subagent": output.get("subagent") or target,
                    "search_query": output.get("search_query"),
                    "search_purpose": output.get("search_purpose") or output.get("information_need"),
                    "selected_tool": output.get("selected_tool"),
                    "anchor_keywords": output.get("anchor_keywords"),
                    "evidence_count": len(evidence),
                    "resolution_status": output.get("resolution_status"),
                }
            )
            structured["keyword_search_results"] = history[-12:]
            sub_results = list(structured.get("subagent_results") or [])
            sub_results.append(
                {
                    "subagent": output.get("subagent") or target,
                    "task_id": task_id,
                    "lookup_intent": output.get("lookup_intent"),
                    "search_query": output.get("search_query"),
                    "selected_tool": output.get("selected_tool"),
                    "evidence_count": len(evidence),
                    "resolution_status": output.get("resolution_status"),
                    "lookup_phase": output.get("lookup_phase"),
                    "source_family": output.get("source_family"),
                }
            )
            if output.get("lookup_research_chain"):
                structured["lookup_research_chain"] = output["lookup_research_chain"]
            from app.orchestrator.lookup_research_chain import merge_chain_updates

            merge_chain_updates(state, output.get("lookup_research_chain_update"))
            if target == "entity_resolution_agent":
                from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
                from app.orchestrator.lookup_research_chain import mark_phase_complete

                if is_fact_lookup_task(state):
                    mark_phase_complete(state, "entity_anchor")
            structured["subagent_results"] = sub_results[-16:]
            state.structured_result = structured
            query_preview = str(output.get("search_query", ""))[:48]
            TraceRecorder.add(
                state,
                f"✓ [A2A] {target} ({task_id}) → {len(evidence)} evidence | {query_preview}",
            )
        elif target == "evidence_curation_planner_agent" and "curation_plan" in output:
            structured = dict(state.structured_result or {})
            structured["curation_plan"] = output["curation_plan"]
            state.structured_result = structured
            TraceRecorder.add(state, "✓ [S7] evidence_curation_planner → plan ready")
        elif target == "claim_relevance_filter_agent":
            structured = dict(state.structured_result or {})
            if "curated_claims" in output:
                structured["curated_claims"] = output["curated_claims"]
            if "excluded_evidence_ids" in output:
                structured["excluded_evidence_ids"] = output["excluded_evidence_ids"]
            state.structured_result = structured
            TraceRecorder.add(
                state,
                f"✓ [S7] claim_relevance_filter → {len(output.get('curated_claims', []))} claims",
            )
        elif target == "evidence_conflict_analyzer_agent":
            structured = dict(state.structured_result or {})
            structured["conflict_notes"] = output.get("conflict_notes", [])
            structured["conflict_analyzed"] = output.get("conflict_analyzed", True)
            state.structured_result = structured
            TraceRecorder.add(state, "✓ [S7] evidence_conflict_analyzer → notes ready")
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
            rendered = draft.render_text().strip()
            if rendered:
                state = self._apply_composition_draft(state, draft)
            elif (state.final_response or "").strip():
                from app.orchestrator.composition_preflight import should_compose_over_clarification

                if should_compose_over_clarification(state):
                    state.limitations.append("Answer composition FINISH 未产生有效正文（已忽略 S5 澄清草稿）")
                else:
                    TraceRecorder.add(state, "✓ [loop] AnswerComposition 完成（保留已有草稿）")
            else:
                state.limitations.append("Answer composition FINISH 未产生有效正文")
            TraceRecorder.add(
                state,
                f"✓ [{policy.state_name}] FINISH_STATE → FinalAnswerDraft",
            )
        elif policy.state_name == "answer_composition" and result is None and not (state.final_response or "").strip():
            state.limitations.append("Answer composition FINISH 缺少 result 且无 final_response")
        elif policy.state_name == "evidence_planning_and_tool_use":
            state.evidence_planning_completed = True
            if action.arguments.get("limitations"):
                state.limitations.extend(action.arguments["limitations"])
            TraceRecorder.add(state, f"✓ [{policy.state_name}] FINISH_STATE → evidence planning complete")
        elif policy.state_name == "evidence_aggregation" and result is not None:
            brief = result if isinstance(result, EvidenceBrief) else EvidenceBrief.model_validate(result)
            apply_evidence_brief(state, brief)
            TraceRecorder.add(state, f"✓ [{policy.state_name}] FINISH_STATE → EvidenceBrief")
        elif action.arguments.get("final_response"):
            state.final_response = action.arguments["final_response"]
        return state

    def _apply_tool_result(
        self,
        state: TravelAgentState,
        action: AgentAction,
        result: ActionResult,
        policy: StateNodePolicy,
    ) -> TravelAgentState:
        evidence = result.output.get("evidence", [])
        if evidence:
            state.evidence = list(state.evidence) + list(evidence)

        trace_payload = result.output.get("tool_traces", [])
        for item in trace_payload:
            if isinstance(item, ToolTrace):
                state.tool_traces.append(item)
            elif isinstance(item, dict):
                state.tool_traces.append(ToolTrace.model_validate(item))

        tool_name = result.output.get("policy_tool_name") or action.target or "tool"
        status = "ok" if result.ok else "error"
        TraceRecorder.add(
            state,
            f"✓ [loop] CALL_TOOL {tool_name} → {len(evidence)} evidence ({status})",
        )
        return state

    def _apply_composition_draft(self, state: TravelAgentState, draft: FinalAnswerDraft) -> TravelAgentState:
        rendered = draft.render_text().strip()
        if rendered:
            state.final_response = rendered
            structured = dict(state.structured_result or {})
            structured["final_answer_draft"] = draft.model_dump()
            if draft.compose_mode == "place_disambiguation":
                structured["s8_place_disambiguation_presented"] = True
                state.next_state = "clarification_response"
                if state.query_understanding:
                    state.query_understanding.needs_clarification = True
                    state.query_understanding.clarification_question = rendered[:800]
            elif draft.compose_mode == "nearby_guided":
                structured["s8_nearby_guided_presented"] = True
            state.structured_result = structured
            TraceRecorder.add(state, "✓ [loop] AnswerComposition 完成")
        elif (state.final_response or "").strip():
            TraceRecorder.add(state, "✓ [loop] AnswerComposition 完成（忽略空草稿）")
        else:
            state.limitations.append("Answer composition 草稿无有效正文")
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
            if key == "information_needs" and value and isinstance(value[0], dict):
                value = [InformationNeed.model_validate(v) for v in value]
            if key == "tool_execution_plan" and isinstance(value, dict):
                value = ToolExecutionPlan.model_validate(value)
            setattr(state, key, value)
        if policy.state_name == "evidence_planning_and_tool_use":
            TraceRecorder.add(state, "✓ [loop] UPDATE_STATE information_needs/planning_notes")
        return state

    @staticmethod
    def _allowed_fields(policy: StateNodePolicy) -> frozenset[str]:
        if policy.state_name == "query_understanding":
            return _QUERY_UNDERSTANDING_FIELDS
        if policy.state_name == "answer_composition":
            return _ANSWER_COMPOSITION_FIELDS
        if policy.state_name == "evidence_planning_and_tool_use":
            return _EVIDENCE_PLANNING_FIELDS
        return frozenset()
