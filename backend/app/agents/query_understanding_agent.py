from app.agents.llm_understanding_agent import LLMUnderstandingSubAgent
from app.agents.normalized_request_to_query_understanding import NormalizedRequestToQueryUnderstanding
from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.config import get_settings
from app.schemas.conversation_context import ConversationContext
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.user_query import UserContext


class QueryUnderstandingAgent:
    """Controlled sub-agent: LLM-first NormalizedUserRequest → QueryUnderstandingResult."""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client
        self.llm_agent = LLMUnderstandingSubAgent(llm_client)
        self.settings = get_settings()

    async def run(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None = None,
        user_ctx: UserContext | None = None,
        place_candidates: list | None = None,
    ) -> QueryUnderstandingResult:
        if self.llm._should_use_anthropic():
            normalized = await self.llm_agent.run(
                raw_query, conversation_context, user_ctx, supported_regions
            )
            return NormalizedRequestToQueryUnderstanding.convert(normalized)

        rule_result = RuleBasedUnderstanding.understand(raw_query, conversation_context, user_ctx)
        return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)
