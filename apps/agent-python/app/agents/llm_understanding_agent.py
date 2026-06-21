import json
import logging
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.agents.normalize_llm_understanding import normalize_llm_understanding_payload
from app.config import get_settings
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.conversation_context import ConversationContext
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.user_query import UserContext
from app.utils.llm_json import parse_llm_json

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _load_system_prompt() -> str:
    system = (PROMPTS_DIR / "llm_understanding.system.md").read_text(encoding="utf-8")
    contract = (PROMPTS_DIR / "llm_understanding.routing_contract.md").read_text(encoding="utf-8")
    return system.replace("{{routing_contract}}", contract)


class LLMUnderstandingSubAgent:
    """LLM-first user request normalization — outputs S3-ready NormalizedUserRequest JSON."""

    def __init__(self, llm_client=None) -> None:
        from app.llm_client import LLMClient

        self.llm = llm_client or LLMClient()
        self.settings = get_settings()
        self._system_prompt = _load_system_prompt()

    async def run(
        self,
        raw_query: str,
        conversation_context: ConversationContext | None = None,
        user_ctx: UserContext | None = None,
        supported_regions: list[str] | None = None,
    ) -> NormalizedUserRequest:
        if not self.llm._should_use_anthropic():
            from app.agents.rule_based_to_normalized_request import RuleBasedToNormalizedRequest

            return RuleBasedToNormalizedRequest.convert(raw_query, conversation_context, user_ctx)

        try:
            return await self._run_with_repair(
                raw_query,
                conversation_context,
                supported_regions,
            )
        except Exception as exc:
            logger.warning("LLM understanding failed, rule-based fallback: %s", exc)
            from app.agents.rule_based_to_normalized_request import RuleBasedToNormalizedRequest

            return RuleBasedToNormalizedRequest.convert(raw_query, conversation_context, user_ctx)

    async def _run_with_repair(
        self,
        raw_query: str,
        conversation_context: ConversationContext | None,
        supported_regions: list[str] | None,
    ) -> NormalizedUserRequest:
        raw = await self._call_llm(raw_query, conversation_context, supported_regions)
        try:
            return self._parse_and_validate(raw, raw_query)
        except (ValidationError, json.JSONDecodeError, ValueError) as first_err:
            logger.warning("NormalizedUserRequest validation failed: %s", first_err)
            repair_tmpl = (PROMPTS_DIR / "llm_understanding.repair.md").read_text(encoding="utf-8")
            repair_user = (
                repair_tmpl.replace("{{validation_error}}", str(first_err))
                .replace("{{raw_user_query}}", raw_query)
            )
            repaired = await self.llm.complete(
                system=self._system_prompt,
                user=repair_user,
                max_tokens=2000,
            )
            return self._parse_and_validate(repaired, raw_query)

    async def _call_llm(
        self,
        raw_query: str,
        conversation_context: ConversationContext | None,
        supported_regions: list[str] | None,
    ) -> str:
        user_tmpl = (PROMPTS_DIR / "llm_understanding.user.md").read_text(encoding="utf-8")
        policy_summary = {
            "forbidden_model_prior": sorted(EvidencePolicy.forbidden_model_prior_claims()),
            "model_prior_allowed_needs": [
                "best_time_to_visit",
                "seasonality",
                "general_travel_advice",
            ],
            "requires_evidence_needs": sorted(EvidencePolicy.forbidden_model_prior_claims()),
        }
        user = (
            user_tmpl.replace("{{raw_user_query}}", raw_query)
            .replace(
                "{{conversation_context}}",
                json.dumps(
                    conversation_context.model_dump() if conversation_context else {},
                    ensure_ascii=False,
                ),
            )
            .replace("{{current_date}}", date.today().isoformat())
            .replace(
                "{{supported_regions}}",
                json.dumps(supported_regions or self.settings.supported_countries, ensure_ascii=False),
            )
            .replace("{{evidence_policy_summary}}", json.dumps(policy_summary, ensure_ascii=False))
        )
        return await self.llm.complete(system=self._system_prompt, user=user, max_tokens=2000)

    @staticmethod
    def _parse_and_validate(raw: str, raw_query: str) -> NormalizedUserRequest:
        data = normalize_llm_understanding_payload(parse_llm_json(raw), raw_query)
        return NormalizedUserRequest.model_validate(data)
