from app.context.conversation_context import ConversationContextBuilder, ConversationMemory
from app.understanding.rewritten_query import RewrittenQueryResult

from .rule_based_understanding import RuleBasedUnderstanding


class ContextualQueryRewriter:
    """Rewrite follow-up queries from conversation context and deterministic understanding."""

    @classmethod
    def rewrite(cls, raw_query: str, memory: ConversationMemory) -> RewrittenQueryResult:
        builder = ConversationContextBuilder()
        ctx = builder.build(None, {"conversation_memory": memory.model_dump()})
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
