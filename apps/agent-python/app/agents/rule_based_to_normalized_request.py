from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.schemas.conversation_context import ConversationContext
from app.schemas.normalized_user_request import (
    AnswerPolicyDraft,
    InformationNeedDraft,
    NormalizedEntity,
    NormalizedTimeScope,
    NormalizedUserConstraints,
    NormalizedUserRequest,
)
from app.schemas.user_query import UserContext


_PLACE_ENTITY_TYPES = frozenset(
    {"attraction", "landmark", "natural_site", "station", "district"}
)


class RuleBasedToNormalizedRequest:
    """Offline / LLM-unavailable fallback — wraps RuleBasedUnderstanding."""

    @classmethod
    def convert(
        cls,
        raw_query: str,
        context: ConversationContext | None,
        user_ctx: UserContext | None = None,
    ) -> NormalizedUserRequest:
        ctx = context or ConversationContext()
        qu = RuleBasedUnderstanding.understand(raw_query, ctx, user_ctx)
        frame = qu.semantic_frame or SemanticFrameBuilder.build(raw_query, qu)

        entities: list[NormalizedEntity] = []
        if frame.entities.country:
            entities.append(
                NormalizedEntity(
                    text=frame.entities.country,
                    normalized_name=frame.entities.country,
                    entity_type="country",
                    country=frame.entities.country,
                    source="unknown",
                    confidence=0.6,
                )
            )
        if frame.entities.city:
            entities.append(
                NormalizedEntity(
                    text=frame.entities.city,
                    normalized_name=frame.entities.city,
                    entity_type="city",
                    country=frame.entities.country,
                    city=frame.entities.city,
                    source="unknown",
                    confidence=0.65,
                )
            )
        for place in frame.entities.places:
            entities.append(
                NormalizedEntity(
                    text=place,
                    normalized_name=place,
                    entity_type="attraction",
                    country=frame.entities.country,
                    city=frame.entities.city,
                    source="unknown",
                    confidence=0.6,
                )
            )

        need_drafts = [
            InformationNeedDraft(need_type=n, priority="medium")
            for n in frame.information_needs
        ]

        return NormalizedUserRequest(
            raw_query=raw_query,
            rewritten_query=qu.rewritten_query,
            intent_summary=qu.rewritten_query,
            query_scope=frame.query_scope.value,
            task_family=frame.task_family.value,
            decision_type=frame.decision_type.value,
            entities=entities,
            time_scope=NormalizedTimeScope(scope=frame.time_scope.value),
            user_constraints=NormalizedUserConstraints(
                constraints=list(frame.user_constraints),
            ),
            information_needs=need_drafts,
            answer_policy=AnswerPolicyDraft(
                requires_live_data=frame.requires_live_data,
                requires_exact_fact=frame.requires_exact_fact,
                can_answer_with_model_prior=frame.can_answer_with_model_prior,
                allow_partial_answer=True,
                should_add_limitations=True,
            ),
            missing_critical_info=list(qu.missing_critical_info),
            needs_clarification=qu.needs_clarification,
            clarification_question=qu.clarification_question,
            confidence=qu.confidence,
        )
