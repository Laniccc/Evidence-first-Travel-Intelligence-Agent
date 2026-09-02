import importlib

from app.context import ConversationContext

from .llm_understanding_agent import LLMUnderstandingSubAgent
from .normalized_request_to_query_understanding import NormalizedRequestToQueryUnderstanding
from .query_understanding_model import QueryUnderstandingResult
from .rule_based_understanding import RuleBasedUnderstanding
from .semantic_frame_builder import SemanticFrameBuilder
from .user_query import UserContext


def get_settings():
    return importlib.import_module("app.config").get_settings()


class QueryUnderstandingAgent:
    """Controlled sub-agent: LLM-first NormalizedUserRequest → QueryUnderstandingResult."""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client
        self.llm_agent = LLMUnderstandingSubAgent(llm_client) if llm_client else None
        self.settings = get_settings()

    async def run(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None = None,
        user_ctx: UserContext | None = None,
        place_candidates: list | None = None,
    ) -> QueryUnderstandingResult:
        if self.llm and self.llm._should_use_anthropic():
            normalized = await self.llm_agent.run(
                raw_query, conversation_context, user_ctx, supported_regions
            )
            return NormalizedRequestToQueryUnderstanding.convert(normalized)

        rule_result = RuleBasedUnderstanding.understand(raw_query, conversation_context, user_ctx)
        return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)
