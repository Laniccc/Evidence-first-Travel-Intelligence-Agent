import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.schemas.conversation_context import ConversationContext
from app.utils.llm_json import parse_llm_json

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

# Semantic geo aliases — independent of mock PLACE_REGISTRY (city/country inference only).
GEO_CITY_ALIASES: dict[str, tuple[str, str]] = {
    "札幌": ("Japan", "Sapporo"),
    "sapporo": ("Japan", "Sapporo"),
    "京都": ("Japan", "Kyoto"),
    "kyoto": ("Japan", "Kyoto"),
    "东京": ("Japan", "Tokyo"),
    "東京": ("Japan", "Tokyo"),
    "tokyo": ("Japan", "Tokyo"),
    "大阪": ("Japan", "Osaka"),
    "osaka": ("Japan", "Osaka"),
    "北京": ("China", "Beijing"),
    "beijing": ("China", "Beijing"),
    "上海": ("China", "Shanghai"),
    "shanghai": ("China", "Shanghai"),
    "成都": ("China", "Chengdu"),
    "chengdu": ("China", "Chengdu"),
    "首尔": ("South Korea", "Seoul"),
    "seoul": ("South Korea", "Seoul"),
    "釜山": ("South Korea", "Busan"),
    "busan": ("South Korea", "Busan"),
    "禾木": ("China", "Altay"),
    "禾木景区": ("China", "Altay"),
    "喀纳斯": ("China", "Altay"),
    "喀纳斯湖": ("China", "Altay"),
    "kanas": ("China", "Altay"),
    "hemu": ("China", "Altay"),
    "新疆": ("China", "Altay"),
    "阿勒泰": ("China", "Altay"),
    "altay": ("China", "Altay"),
}

_POI_SUFFIX_PATTERN = re.compile(r"(塔|寺|宫|公园|塔|神社|城|博物馆|塔|tower|temple|shrine|palace|park)", re.I)


class PlaceMention(BaseModel):
    text: str
    entity_type: str = "unknown"  # city | country | poi | region
    country: str | None = None
    city: str | None = None
    confidence: float = 0.7
    metadata: dict = Field(default_factory=dict)


class LLMPlaceEntityExtractor:
    """LLM-first place/city/country mention extraction — not fact lookup."""

    def __init__(self, llm_client=None) -> None:
        from app.llm_client import LLMClient

        self.llm = llm_client or LLMClient()

    async def extract(self, raw_query: str, context: ConversationContext | None = None) -> list[PlaceMention]:
        from app.config import get_settings

        if self.llm._should_use_anthropic():
            try:
                mentions = await self._llm_extract(raw_query, context)
                if mentions:
                    return mentions
            except Exception as exc:
                logger.warning("LLM place extraction failed: %s", exc)
            if not get_settings().place_resolution_use_mock:
                return []
        return self.extract_sync(raw_query, context)

    @classmethod
    def extract_sync(cls, raw_query: str, context: ConversationContext | None = None) -> list[PlaceMention]:
        text = raw_query.strip()
        mentions: list[PlaceMention] = []
        seen: set[str] = set()

        for alias, (country, city) in sorted(GEO_CITY_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in text or alias.lower() in text.lower():
                key = f"city:{city}"
                if key not in seen:
                    mentions.append(
                        PlaceMention(
                            text=alias,
                            entity_type="city",
                            country=country,
                            city=city,
                            confidence=0.88,
                        )
                    )
                    seen.add(key)

        poi = cls._detect_poi_mention(text, mentions)
        if poi:
            key = f"poi:{poi.text}"
            if key not in seen:
                mentions.append(poi)
                seen.add(key)

        if context and context.last_city and not any(m.entity_type == "city" for m in mentions):
            mentions.append(
                PlaceMention(
                    text=context.last_city,
                    entity_type="city",
                    country=context.last_country,
                    city=context.last_city,
                    confidence=0.6,
                    metadata={"from_session": True},
                )
            )

        return mentions

    @classmethod
    def _detect_poi_mention(cls, text: str, city_mentions: list[PlaceMention]) -> PlaceMention | None:
        if not _POI_SUFFIX_PATTERN.search(text):
            return None
        country = city_mentions[0].country if city_mentions else None
        city = city_mentions[0].city if city_mentions else None
        for alias in sorted(GEO_CITY_ALIASES.keys(), key=len, reverse=True):
            if alias in text:
                idx = text.find(alias)
                poi_text = text[idx:].split("？")[0].split("?")[0].strip()
                if len(poi_text) > len(alias):
                    return PlaceMention(
                        text=poi_text,
                        entity_type="poi",
                        country=country,
                        city=city,
                        confidence=0.75,
                    )
        if _POI_SUFFIX_PATTERN.search(text):
            return PlaceMention(text=text, entity_type="poi", country=country, city=city, confidence=0.55)
        return None

    async def _llm_extract(self, raw_query: str, context: ConversationContext | None) -> list[PlaceMention]:
        system = (
            "Extract geographic entities from a travel query. Return JSON only:\n"
            '{"mentions":[{"text":"...","entity_type":"city|country|poi|region","country":"...","city":"...","confidence":0.0}]}\n'
            "Rules:\n"
            "- Infer city/country from semantics; do NOT require a fixed place registry.\n"
            "- Identifying a POI does NOT mean you know opening hours or prices.\n"
            "- For seasonal questions (e.g. 札幌适合几月份去), entity_type=city.\n"
        )
        user = json.dumps(
            {
                "raw_query": raw_query,
                "conversation_context": context.model_dump() if context else {},
            },
            ensure_ascii=False,
        )
        raw = await self.llm.complete(system=system, user=user, max_tokens=600)
        data = parse_llm_json(raw)
        return [PlaceMention.model_validate(m) for m in data.get("mentions", [])]
