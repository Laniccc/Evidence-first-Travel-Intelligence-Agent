import json
import logging
from datetime import datetime

from app.policies.evidence_policy import EvidencePolicy
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.semantic_frame import DecisionType, SemanticFrame
from tools.base import BaseTravelTool

logger = logging.getLogger(__name__)

MODEL_PRIOR_LIMITATION = (
    "该建议基于一般旅行常识，不代表具体年份天气、交通、景区开放、活动日期或价格情况。"
)

_CITY_SEASON_PRIORS: dict[str, str] = {
    "Sapporo": (
        "札幌季节概览（一般规律）：\n"
        "• 看雪/冬季氛围：1–2 月（雪祭前后较热闹，但寒冷）\n"
        "• 避暑/自然风光：6–8 月（凉爽舒适，适合户外）\n"
        "• 秋季舒适/红叶：9–10 月\n"
        "• 过渡季：3–4 月、11 月体验相对不稳定，天气多变"
    ),
}


class KnowledgePriorTool(BaseTravelTool):
    """Low-confidence advisory evidence from general travel knowledge — never for hard facts."""

    name = "knowledge_prior"
    MAX_CONFIDENCE = 0.6

    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client

    async def run(
        self,
        raw_query: str | None = None,
        semantic_frame: SemanticFrame | None = None,
        limitations: list[str] | None = None,
        **kwargs,
    ) -> list[Evidence]:
        frame = semantic_frame or kwargs.get("frame")
        query = raw_query or (frame.raw_query if frame else "")
        if not frame:
            raise ValueError("KnowledgePriorTool requires SemanticFrame")

        for need in frame.information_needs:
            if need in EvidencePolicy.forbidden_model_prior_claims():
                raise ValueError(f"KnowledgePriorTool cannot generate claim for {need}")

        allowed_needs = [
            n for n in frame.information_needs if EvidencePolicy.model_prior_allowed_for(n)
        ]
        if not allowed_needs and frame.decision_type not in {
            DecisionType.BEST_TIME_TO_VISIT,
            DecisionType.GENERAL_ADVICE,
        }:
            raise ValueError("No model-prior-allowed information needs for this query")

        content = await self._generate_content(query, frame)
        country = frame.entities.country or ""
        city = frame.entities.city
        place = frame.entities.places[0] if frame.entities.places else None

        claim_type = (
            ClaimType.BEST_TIME_TO_VISIT
            if frame.decision_type == DecisionType.BEST_TIME_TO_VISIT
            else ClaimType.TRAVEL_ADVICE
        )

        ev_limitations = [MODEL_PRIOR_LIMITATION]
        if limitations:
            ev_limitations.extend(limitations)

        evidence = Evidence(
            source_name="Travel Knowledge Prior (LLM)",
            source_type=SourceType.MODEL_PRIOR,
            source_url=None,
            country=country,
            city=city,
            place_name=place,
            retrieved_at=datetime.utcnow(),
            data_freshness=DataFreshness.STALE,
            license_scope=LicenseScope.UNKNOWN,
            confidence=self.MAX_CONFIDENCE,
            claims=[
                Claim(
                    claim_type=claim_type,
                    value=content,
                    normalized_value={
                        "advice": content,
                        "decision_type": frame.decision_type.value,
                        "information_needs": allowed_needs or frame.information_needs,
                        "source_type": SourceType.MODEL_PRIOR.value,
                        "confidence": self.MAX_CONFIDENCE,
                    },
                    confidence=self.MAX_CONFIDENCE,
                )
            ],
            limitations=ev_limitations,
        )
        return [evidence]

    async def _generate_content(self, query: str, frame: SemanticFrame) -> str:
        city = frame.entities.city
        place = frame.entities.places[0] if frame.entities.places else None
        if frame.decision_type == DecisionType.BEST_TIME_TO_VISIT and city and city in _CITY_SEASON_PRIORS:
            return _CITY_SEASON_PRIORS[city]

        if self.llm and self.llm._should_use_anthropic():
            try:
                system = (
                    "You provide low-confidence seasonal travel advice as JSON: "
                    '{"advice": "..."}. Do NOT invent opening hours, ticket prices, '
                    "today's weather, or current crowd levels."
                )
                place = frame.entities.places[0] if frame.entities.places else None
                user = json.dumps(
                    {
                        "query": query,
                        "city": frame.entities.city,
                        "country": frame.entities.country,
                        "place": place,
                        "decision_type": frame.decision_type.value,
                    },
                    ensure_ascii=False,
                )
                raw = await self.llm.complete(system=system, user=user, max_tokens=600)
                data = json.loads(raw)
                return str(data.get("advice", raw))
            except Exception as exc:
                logger.warning("KnowledgePrior LLM failed: %s", exc)

        target = place or city or frame.entities.country or "该目的地"
        return (
            f"关于「{query}」：{target} 的旅行建议需结合季节与个人偏好。"
            "一般而言，旺季与淡季在天气、人流与价格上差异明显；"
            "建议出发前查阅当年气候与节庆安排。"
        )
