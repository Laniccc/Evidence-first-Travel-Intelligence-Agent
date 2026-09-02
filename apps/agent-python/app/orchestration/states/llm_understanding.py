import re
from typing import Any, Callable, Protocol

from app.context.conversation_context import ConversationContextBuilder
from app.context.conversation_context import ConversationContext
from app.governance.failure_reason import FailureClass
from app.observability.trace import TraceRecorder
from app.orchestration._legacy_boundary import legacy_config_attr
from app.orchestration.clarification_gate import ClarificationGate
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)
from app.understanding.llm_understanding_agent import LLMUnderstandingSubAgent
from app.understanding.normalized_request_to_query_understanding import NormalizedRequestToQueryUnderstanding
from app.understanding.normalized_request_to_semantic_frame import NormalizedRequestToSemanticFrame
from app.understanding.normalized_request_to_travel_task import NormalizedRequestToTravelTask
from app.understanding.rewritten_query import RewrittenQueryResult
from app.understanding.normalized_user_request import NormalizedUserRequest
from app.understanding.place_candidate import PlaceCandidate, PlaceResolutionSource
from app.understanding.rule_based_to_normalized_request import RuleBasedToNormalizedRequest

get_settings = legacy_config_attr("get_settings")
TravelAgentState = Any
UserContext = Any


class LLMUnderstandingState:
    """S2: LLM-first understanding → NormalizedUserRequest → SemanticFrame / TravelTask."""

    def __init__(self, llm_client) -> None:
        self.context_builder = ConversationContextBuilder()
        self.agent = LLMUnderstandingSubAgent(llm_client)
        self.settings = get_settings()

    async def run(
        self,
        state: TravelAgentState,
        user_ctx: UserContext,
        user_context: dict | None = None,
    ) -> TravelAgentState:
        context = self.context_builder.build(state, user_context, user_ctx)
        state.conversation_context = context
        TraceRecorder.add(state, "✓ 已构建会话上下文")

        normalized = await self.agent.run(
            state.raw_user_query,
            context,
            user_ctx,
            supported_regions=self.settings.supported_countries,
        )
        state.normalized_request = normalized

        using_llm = self.agent.llm._should_use_anthropic()
        mode_label = "LLM"

        frame = NormalizedRequestToSemanticFrame.convert(normalized)
        task = NormalizedRequestToTravelTask.convert(normalized, user_ctx)
        qu = NormalizedRequestToQueryUnderstanding.convert(normalized, frame, task)

        state.semantic_frame = frame
        state.travel_task = task
        state.query_understanding = qu
        state.rewritten_query_result = RewrittenQueryResult(
            rewritten_query=qu.rewritten_query,
            resolved_references=qu.resolved_references,
            missing_critical_info=qu.missing_critical_info,
            needs_clarification=qu.needs_clarification,
            clarification_prompt=qu.clarification_question,
            assumptions=qu.assumptions,
            confidence=qu.confidence,
            key_concerns=qu.key_concerns,
        )

        TraceRecorder.add(state, f"✓ 用户理解完成（{mode_label}）：{normalized.rewritten_query[:80]}")
        TraceRecorder.add(
            state,
            f"✓ NormalizedUserRequest：{normalized.query_scope}/{normalized.task_family}/"
            f"{normalized.decision_type} (confidence={normalized.confidence:.2f})",
        )
        if normalized.entities:
            names = ", ".join(e.normalized_name or e.text for e in normalized.entities[:3])
            TraceRecorder.add(state, f"✓ 识别实体：{names}")
        TraceRecorder.add(
            state,
            f"✓ SemanticFrame：{frame.query_scope.value}/{frame.decision_type.value}",
        )
        TraceRecorder.add(state, f"✓ 已生成 TravelTask：{task.task_type.value}")

        if ClarificationGate.apply(state):
            return state

        state.next_state = "continue"
        return state


class PrimaryUnderstanding(Protocol):
    async def normalize(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        *,
        repair: bool,
    ) -> NormalizedUserRequest | dict[str, Any]: ...


RuleFallback = Callable[
    [str, ConversationContext],
    NormalizedUserRequest | dict[str, Any],
]
AttractionMatcher = Callable[[str], list[Any]]


class UnderstandingHandler:
    """LLM parse → one repair → deterministic rule fallback → clarification."""

    def __init__(
        self,
        *,
        primary: PrimaryUnderstanding | None = None,
        rule_fallback: RuleFallback | None = None,
        attraction_matcher: AttractionMatcher | None = None,
    ) -> None:
        self._primary = primary
        self._rule = rule_fallback
        self._attraction_matcher = attraction_matcher

    async def run(self, context: StateContext) -> StateResult:
        snapshot = context.artifacts.get(AgentState.CONTEXT.value, {}).get("snapshot", {})
        conversation = ConversationContext.model_validate(
            snapshot.get("conversation_context") or {}
        )
        attempts: list[str] = []

        if self._primary is not None:
            attempts.append("model")
            try:
                request = await self._normalize_primary(context.raw_query, conversation, repair=False)
                return self._result(request, attempts=attempts)
            except Exception:
                attempts.append("repair")
                try:
                    request = await self._normalize_primary(context.raw_query, conversation, repair=True)
                    return self._result(
                        request,
                        attempts=attempts,
                        recovery=RecoveryRecord(
                            strategy="llm_repair_once",
                            recovered_from=FailureClass.PARSE_ERROR,
                            attempt=2,
                        ),
                    )
                except Exception:
                    pass

        attempts.append("rule")
        try:
            if self._rule is not None:
                raw_request = self._rule(context.raw_query, conversation)
            else:
                raw_request = RuleBasedToNormalizedRequest.convert(
                    context.raw_query,
                    conversation,
                    place_candidates=self._catalog_candidates(context.raw_query),
                )
            request = NormalizedUserRequest.model_validate(raw_request)
            request = self._enrich_from_catalog(context.raw_query, request)
        except Exception:
            return StateResult(
                status="recovered",
                next_state=AgentState.CLARIFICATION,
                output={
                    "understanding_attempts": attempts,
                    "reason": "understanding_unavailable",
                    "question": "请明确景点名称，以及你想查询事实、适合度还是进行比较。",
                },
                recovery=RecoveryRecord(
                    strategy="clarification",
                    recovered_from=FailureClass.PARSE_ERROR,
                    attempt=len(attempts),
                ),
            )

        recovery = None
        if self._primary is not None:
            recovery = RecoveryRecord(
                strategy="rule_fallback",
                recovered_from=FailureClass.PARSE_ERROR,
                attempt=len(attempts),
            )
        return self._result(request, attempts=attempts, recovery=recovery)

    def _catalog_candidates(self, query: str) -> list[PlaceCandidate] | None:
        if self._attraction_matcher is None:
            return None
        return [
            PlaceCandidate(
                mention=item.name,
                canonical_name=item.name,
                country=getattr(item, "country", None),
                city=getattr(item, "city", None),
                place_type="poi",
                confidence=1.0,
                resolution_source=PlaceResolutionSource.LOCAL_CACHE,
                metadata={"attraction_id": item.attraction_id},
            )
            for item in self._attraction_matcher(query)
        ]

    def _enrich_from_catalog(
        self,
        query: str,
        request: NormalizedUserRequest,
    ) -> NormalizedUserRequest:
        if self._attraction_matcher is None:
            return request
        matches = self._attraction_matcher(query)
        if not matches:
            return request

        from app.understanding.normalized_user_request import (
            InformationNeedDraft,
            NormalizedEntity,
        )

        entities = [
            NormalizedEntity(
                text=item.name,
                normalized_name=item.name,
                entity_type="attraction",
                country=getattr(item, "country", None),
                city=getattr(item, "city", None),
                source="user_explicit",
                confidence=1.0,
            )
            for item in matches
        ]
        family = request.task_family
        decision = request.decision_type
        needs = list(request.information_needs)
        if family != "planning" and len(matches) == 2 and re.search(
            r"(比较|对比|哪个|还是|\bvs\b)", query, re.I
        ):
            family = "comparison"
            decision = "how_to_choose"
        elif family != "planning" and re.search(
            r"(几点|开放时间|开馆|闭馆|关门|门票|票价|预约)", query
        ):
            family = "fact_lookup"
            if re.search(r"(几点|开放时间|开馆|闭馆|关门)", query):
                decision = "opening_hours"
                needs = [InformationNeedDraft(need_type="opening_hours", priority="required")]
            elif re.search(r"(门票|票价)", query):
                decision = "ticket_price"
                needs = [InformationNeedDraft(need_type="ticket_price", priority="required")]
            else:
                needs = [InformationNeedDraft(need_type="reservation", priority="required")]
        elif family not in {"comparison", "planning"}:
            family = "suitability"

        return request.model_copy(
            update={
                "query_scope": "place",
                "task_family": family,
                "decision_type": decision,
                "entities": entities,
                "information_needs": needs,
                "missing_critical_info": [],
                "needs_clarification": False,
                "clarification_question": None,
            }
        )

    async def _normalize_primary(
        self,
        query: str,
        conversation: ConversationContext,
        *,
        repair: bool,
    ) -> NormalizedUserRequest:
        raw = await self._primary.normalize(query, conversation, repair=repair)
        return NormalizedUserRequest.model_validate(raw)

    @staticmethod
    def _result(
        request: NormalizedUserRequest,
        *,
        attempts: list[str],
        recovery: RecoveryRecord | None = None,
    ) -> StateResult:
        next_state = AgentState.CLARIFICATION if request.needs_clarification else AgentState.ROUTE
        output = {
            "normalized_request": request.model_dump(mode="json"),
            "understanding_attempts": attempts,
        }
        if recovery:
            return StateResult(
                status="recovered",
                next_state=next_state,
                output=output,
                recovery=recovery,
            )
        return StateResult.succeeded(next_state=next_state, output=output)
