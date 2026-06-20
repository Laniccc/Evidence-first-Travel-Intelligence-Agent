import json
from datetime import date
from pathlib import Path

from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.catalog.place_catalog import get_place_catalog
from app.config import get_settings
from app.schemas.conversation_context import ConversationContext
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.user_query import UserContext

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class QueryUnderstandingAgent:
    """Controlled sub-agent: rewrite + resolve references + TravelTask draft only."""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client
        self.catalog = get_place_catalog()
        self.settings = get_settings()

    async def run(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None = None,
        user_ctx: UserContext | None = None,
    ) -> QueryUnderstandingResult:
        rule_result = RuleBasedUnderstanding.understand(raw_query, conversation_context, user_ctx)

        if rule_result.needs_clarification:
            SemanticFrameBuilder.attach(raw_query, rule_result)
            return rule_result

        if not RuleBasedUnderstanding.needs_llm(raw_query, rule_result):
            return rule_result

        if not self.llm._should_use_anthropic():
            SemanticFrameBuilder.attach(raw_query, rule_result)
            return rule_result

        try:
            llm_result = await self._llm_understand(raw_query, conversation_context, supported_regions)
            SemanticFrameBuilder.attach(raw_query, llm_result)
            return llm_result
        except Exception:
            SemanticFrameBuilder.attach(raw_query, rule_result)
            return rule_result

    async def _llm_understand(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None,
    ) -> QueryUnderstandingResult:
        system = (PROMPTS_DIR / "query_understanding.system.md").read_text(encoding="utf-8")
        user_tmpl = (PROMPTS_DIR / "query_understanding.user.md").read_text(encoding="utf-8")
        hints = self.catalog.list_known_places(limit=25)

        user = (
            user_tmpl.replace("{{raw_user_query}}", raw_query)
            .replace("{{conversation_context}}", conversation_context.model_dump_json())
            .replace("{{supported_regions}}", json.dumps(supported_regions or self.settings.supported_countries))
            .replace("{{known_place_hints}}", json.dumps(hints))
            .replace("{{current_date}}", date.today().isoformat())
        )
        raw = await self.llm.complete(system=system, user=user, max_tokens=1500)
        data = json.loads(raw)
        return QueryUnderstandingResult.model_validate(data)
