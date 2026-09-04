import asyncio
import re
from typing import Any, Callable, Protocol

from app.context.conversation_context import ConversationContext
from app.governance.failure_reason import FailureClass
from app.integrations.llm.client import ModelTransportError
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)
from app.understanding.normalized_user_request import NormalizedUserRequest
from app.understanding.place_candidate import PlaceCandidate, PlaceResolutionSource
from app.understanding.rule_based_to_normalized_request import RuleBasedToNormalizedRequest


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
        primary_timeout_seconds: float = 8.0,
    ) -> None:
        self._primary = primary
        self._rule = rule_fallback
        self._attraction_matcher = attraction_matcher
        if primary_timeout_seconds <= 0:
            raise ValueError("primary timeout must be positive")
        self._primary_timeout = primary_timeout_seconds

    async def run(self, context: StateContext) -> StateResult:
        snapshot = context.artifacts.get(AgentState.CONTEXT.value, {}).get("snapshot", {})
        conversation = ConversationContext.model_validate(
            snapshot.get("conversation_context") or {}
        )
        attempts: list[str] = []
        failures: list[dict[str, Any]] = []
        category = FailureClass.PARSE_ERROR

        if self._primary is not None:
            try:
                # One shared deadline for model + repair; no nested transport retries.
                async with asyncio.timeout(self._primary_timeout):
                    for repair in (False, True):
                        attempts.append("repair" if repair else "model")
                        try:
                            request = await self._normalize_primary(context.raw_query, conversation, repair=repair)
                        except ValueError:
                            failures.append({"attempt": len(attempts), "code": "llm_schema_invalid",
                                             "category": FailureClass.PARSE_ERROR.value})
                            continue
                        return self._result(
                            request, attempts=attempts, failures=failures,
                            recovery=RecoveryRecord(strategy="llm_repair_once",
                                recovered_from=FailureClass.PARSE_ERROR, attempt=2) if repair else None,
                        )
            except Exception as exc:
                if isinstance(exc, ModelTransportError):
                    code = exc.code.value
                    category = {
                        "llm_auth_failed": FailureClass.POLICY_DENIED,
                        "llm_credentials_missing": FailureClass.POLICY_DENIED,
                        "llm_rate_limited": FailureClass.RATE_LIMIT,
                        "llm_timeout": FailureClass.TIMEOUT,
                    }.get(code, FailureClass.DEPENDENCY_UNAVAILABLE)
                elif isinstance(exc, TimeoutError):
                    code, category = "llm_timeout", FailureClass.TIMEOUT
                else:
                    code, category = "llm_unavailable", FailureClass.DEPENDENCY_UNAVAILABLE
                failures.append({"attempt": len(attempts), "code": code, "category": category.value})

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
            request = self._enrich_from_catalog(
                context.raw_query, request, conversation=conversation
            )
            if self._primary is not None and not request.needs_clarification:
                expected = 2 if request.task_family == "comparison" else 1
                names = {e.normalized_name or e.text for e in request.entities
                         if e.entity_type in {"attraction", "landmark", "natural_site"}}
                if request.task_family not in {"fact_lookup", "suitability", "comparison"} or len(names) != expected:
                    request = request.model_copy(update={
                        "needs_clarification": True,
                        "clarification_question": "请明确景点名称，以及需要查询的事实、适合度或比较条件。",
                    })
        except Exception:
            return StateResult(
                status="recovered",
                next_state=AgentState.CLARIFICATION,
                output={
                    "understanding_attempts": attempts,
                    "reason": "understanding_unavailable",
                    "question": "请明确景点名称，以及你想查询事实、适合度还是进行比较。",
                    "understanding_path": "clarification",
                    "understanding_failures": failures,
                    "understanding_versions": self._versions(),
                },
                recovery=RecoveryRecord(
                    strategy="clarification",
                    recovered_from=category,
                    attempt=len(attempts),
                ),
            )

        recovery = None
        if self._primary is not None:
            recovery = RecoveryRecord(
                strategy="rule_fallback",
                recovered_from=category,
                attempt=len(attempts),
            )
        return self._result(request, attempts=attempts, recovery=recovery, failures=failures)

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
        *,
        conversation: ConversationContext | None = None,
    ) -> NormalizedUserRequest:
        if self._attraction_matcher is None:
            return request
        matches = self._attraction_matcher(query)
        if not matches and conversation and re.search(r"(它|这个|那里|该景点)", query):
            for previous in conversation.last_places:
                previous_name = (
                    previous
                    if isinstance(previous, str)
                    else getattr(previous, "canonical_name", None)
                    or getattr(previous, "name", None)
                    or getattr(previous, "mention", None)
                )
                if previous_name:
                    matches.extend(self._attraction_matcher(str(previous_name)))
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

    def _versions(self) -> dict[str, str]:
        return dict(getattr(self._primary, "audit_versions", {}))

    def _result(
        self,
        request: NormalizedUserRequest,
        *,
        attempts: list[str],
        recovery: RecoveryRecord | None = None,
        failures: list[dict[str, Any]] | None = None,
    ) -> StateResult:
        next_state = AgentState.CLARIFICATION if request.needs_clarification else AgentState.ROUTE
        output = {
            "normalized_request": request.model_dump(mode="json"),
            "understanding_attempts": attempts,
            "understanding_path": "clarification" if request.needs_clarification else attempts[-1],
            "understanding_failures": failures or [],
            "understanding_versions": self._versions(),
        }
        if request.needs_clarification:
            output["question"] = request.clarification_question or "请明确景点名称和查询条件。"
        if recovery:
            return StateResult(
                status="recovered",
                next_state=next_state,
                output=output,
                recovery=recovery,
            )
        return StateResult.succeeded(next_state=next_state, output=output)
