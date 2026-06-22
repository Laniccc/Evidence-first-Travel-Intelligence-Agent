import re

from app.catalog.location_resolver import iter_city_country, iter_location_aliases, resolve_start_location
from app.catalog.place_catalog import get_place_catalog
from app.schemas.user_query import (
    BudgetLevel,
    IntentType,
    PartyType,
    PaceType,
    RegionGateResult,
    TransportPreference,
    UserContext,
    UserGoal,
)


class RegionGateAgent:
    COUNTRY_KEYWORDS = {
        "Japan": ["日本", "japan", "东京", "京都", "大阪", "奈良", "札幌", "冈山", "冲绳", "箱根", "新宿", "清水寺", "伏见", "岚山"],
        "China": ["中国", "china", "北京", "上海", "杭州", "苏州", "西安", "成都", "故宫", "颐和园", "天坛"],
        "South Korea": ["韩国", "korea", "south korea", "首尔", "釜山", "济州", "明洞", "景福宫", "北村", "南山塔"],
    }

    @classmethod
    def run(cls, query: str) -> RegionGateResult:
        lower = query.lower()
        scores = {country: 0 for country in cls.COUNTRY_KEYWORDS}
        city = None
        for country, keywords in cls.COUNTRY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in lower:
                    scores[country] += 1
        for alias, (country, city_name, _) in iter_location_aliases():
            if alias.lower() in lower:
                scores[country] += 2
                city = city_name
        for c_key, (country, city_name) in iter_city_country():
            if c_key in lower:
                scores[country] += 2
                city = city_name
        best_country = max(scores, key=scores.get)
        if scores[best_country] == 0:
            return RegionGateResult(
                supported=False,
                reason="Current version focuses on Japan, China, and South Korea only.",
            )
        return RegionGateResult(supported=True, country=best_country, city=city, reason=f"Detected focus region: {best_country}")


class IntentAgent:
    COMPARE_MARKERS = ["哪个更", "哪个适合", "比较", "对比", "vs", "还是"]
    ITINERARY_MARKERS = ["安排", "行程", "一天", "半日", "路线", "轻松玩", "文化游"]
    WEATHER_MARKERS = ["明天", "天气", "下雨", "适合去吗"]

    @classmethod
    async def run(cls, query: str, llm_client, user_context: UserContext | None = None) -> UserGoal:
        parsed = cls.parse_deterministic(query, user_context)
        if llm_client._should_use_anthropic():
            try:
                raw = await llm_client.complete(
                    system="Parse travel intent into JSON with keys: intent_type, destination_country, destination_city, place_candidates, party, pace, preferences, constraints, start_location, travel_date.",
                    user=query,
                )
                import json

                data = json.loads(raw)
                parsed.intent_type = IntentType(data.get("intent_type", parsed.intent_type))
            except Exception:
                pass
        return parsed

    @classmethod
    def parse_deterministic(cls, query: str, user_context: UserContext | None = None) -> UserGoal:
        catalog = get_place_catalog()
        region = RegionGateAgent.run(query)
        places = catalog.find_places_in_text(query)
        intent = IntentType.SINGLE_PLACE
        if any(m in query for m in cls.COMPARE_MARKERS) or (len(places) >= 2 and "哪个" in query):
            intent = IntentType.COMPARE_PLACES
        elif any(m in query for m in cls.ITINERARY_MARKERS):
            intent = IntentType.ITINERARY
        elif any(m in query for m in cls.WEATHER_MARKERS) and len(places) == 1 and not any(x in query for x in ["适合", "值得", "推荐"]):
            intent = IntentType.WEATHER_RISK

        party: list[PartyType] = []
        if any(x in query for x in ["父母", "老人", "长辈", "elderly"]):
            party.append(PartyType.ELDERLY)
        if any(x in query for x in ["情侣", "couple"]):
            party.append(PartyType.COUPLE)
        if any(x in query for x in ["亲子", "孩子", "儿童", "family"]):
            party.append(PartyType.FAMILY)

        pace = PaceType.RELAXED if any(x in query for x in ["轻松", "不想太累", "别太累"]) else PaceType.UNKNOWN
        start_location = None
        for alias, (_, _, loc) in iter_location_aliases():
            if alias in query or alias.lower() in query.lower():
                start_location = loc
                break
        m = re.search(r"住在(.{1,12})", query)
        if m:
            start_location = m.group(1).strip("，。 ")
        if start_location:
            resolved = resolve_start_location(start_location)
            if resolved:
                start_location = resolved[2]

        ctx = user_context or UserContext()
        normalized_query_place = catalog.normalize_place_name(query)
        return UserGoal(
            intent_type=intent,
            destination_country=region.country,
            destination_city=region.city,
            place_candidates=places or ([normalized_query_place] if normalized_query_place else []),
            travel_date=ctx.travel_date,
            start_location=ctx.start_location or start_location,
            party=ctx.party or party,
            budget_level=ctx.budget_level,
            pace=ctx.pace if ctx.pace != PaceType.UNKNOWN else pace,
            transport_preference=ctx.transport_preference,
            preferences=ctx.preferences,
            constraints=ctx.constraints,
        )
