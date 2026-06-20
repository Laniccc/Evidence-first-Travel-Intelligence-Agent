import json
from datetime import date
from pathlib import Path

from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.catalog.place_resolver import resolve_places_for_query
from app.config import get_settings
from app.schemas.conversation_context import ConversationContext
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.user_query import UserContext

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class QueryUnderstandingAgent:
    """Controlled sub-agent: rewrite + resolve references + TravelTask + SemanticFrame."""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client
        self.settings = get_settings()

    async def run(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None = None,
        user_ctx: UserContext | None = None,
    ) -> QueryUnderstandingResult:
        place_candidates = await resolve_places_for_query(raw_query, conversation_context, self.llm)
        rule_result = RuleBasedUnderstanding.understand(raw_query, conversation_context, user_ctx)

        if rule_result.needs_clarification:
            return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)

        if not RuleBasedUnderstanding.needs_llm(raw_query, rule_result):
            return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)

        if not self.llm._should_use_anthropic():
            return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)

        try:
            llm_result = await self._llm_understand(
                raw_query, conversation_context, supported_regions, place_candidates
            )
            return SemanticFrameBuilder.ensure_result(raw_query, llm_result, place_candidates)
        except Exception:
            return SemanticFrameBuilder.ensure_result(raw_query, rule_result, place_candidates)

    async def _llm_understand(
        self,
        raw_query: str,
        conversation_context: ConversationContext,
        supported_regions: list[str] | None,
        place_candidates: list,
    ) -> QueryUnderstandingResult:
        system = (PROMPTS_DIR / "query_understanding.system.md").read_text(encoding="utf-8")
        user_tmpl = (PROMPTS_DIR / "query_understanding.user.md").read_text(encoding="utf-8")
        entity_hints = [
            {
                "mention": c.mention,
                "type": c.place_type,
                "city": c.city,
                "country": c.country,
                "source": c.resolution_source.value,
            }
            for c in place_candidates
        ]

        user = (
            user_tmpl.replace("{{raw_user_query}}", raw_query)
            .replace("{{conversation_context}}", conversation_context.model_dump_json())
            .replace("{{supported_regions}}", json.dumps(supported_regions or self.settings.supported_countries))
            .replace("{{entity_hints}}", json.dumps(entity_hints, ensure_ascii=False))
            .replace("{{current_date}}", date.today().isoformat())
        )
        raw = await self.llm.complete(system=system, user=user, max_tokens=1500)
        data = json.loads(raw)
        return QueryUnderstandingResult.model_validate(data)
