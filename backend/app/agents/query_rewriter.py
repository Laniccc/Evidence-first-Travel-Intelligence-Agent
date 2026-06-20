from app.agents.conversation_context_builder import ConversationContextBuilder
from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.rewritten_query import RewrittenQueryResult


class ContextualQueryRewriter:
    """Backward-compatible wrapper over RuleBasedUnderstanding."""

    @classmethod
    def rewrite(cls, raw_query: str, memory: ConversationMemory) -> RewrittenQueryResult:
        builder = ConversationContextBuilder()
        from app.schemas.user_query import TravelAgentState

        state = TravelAgentState(session_id="legacy", query_id="legacy", raw_user_query=raw_query)
        ctx = builder.build(state, {"conversation_memory": memory.model_dump()})
        result = RuleBasedUnderstanding.understand(raw_query, ctx)
        return RewrittenQueryResult(
            rewritten_query=result.rewritten_query,
            resolved_references=result.resolved_references,
            missing_critical_info=result.missing_critical_info,
            needs_clarification=result.needs_clarification,
            clarification_prompt=result.clarification_question,
            assumptions=result.assumptions,
            confidence=result.confidence,
            key_concerns=result.key_concerns,
        )
