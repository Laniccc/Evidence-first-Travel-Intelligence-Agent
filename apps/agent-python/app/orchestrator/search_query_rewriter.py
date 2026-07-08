"""Claim-driven query rewrite: entity + intent + source/time hints → multi-query search plan."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from app.schemas.intent_profile import PrimaryIntent
from app.schemas.search_query_plan import SearchQueryPlanItem
from app.schemas.search_task import SearchTask
from app.schemas.semantic_frame import TimeScope
from app.schemas.user_query import TravelAgentState

_CLAIM_ALIASES = {
    "altitude": "elevation",
    "general_travel_advice": "open_advice",
}

# claim → diverse query angles (place/city/region/time filled at runtime)
_CLAIM_QUERY_ANGLES: dict[str, list[dict]] = {
    "ticket_price": [
        {"q": "{place} 门票 官方", "goal": "查景区官方门票信息", "source": "official"},
        {"q": "{place} 票价 官网", "goal": "查官网票价页面", "source": "official"},
        {"q": "{city} {place} 门票", "goal": "带城市限定查门票", "source": "official"},
        {"q": "{place} 游客服务 门票", "goal": "查游客服务中心票价说明", "source": "official"},
    ],
    "opening_hours": [
        {"q": "{place} 开放时间 官方", "goal": "查官方开放时间", "source": "official"},
        {"q": "{place} 营业时间", "goal": "查营业时间", "source": "official"},
        {"q": "{city} {place} 开放时间", "goal": "带城市限定查开放时间", "source": "official"},
        {"q": "{place} 闭园时间", "goal": "查闭园时间", "source": "official"},
    ],
    "elevation": [
        {"q": "{region} {place} 海拔", "goal": "查海拔（米）", "source": "web"},
        {"q": "{place} 海拔高度", "goal": "查海拔高度", "source": "web"},
        {"q": "{city} {place} 海拔", "goal": "查海拔（带行政区）", "source": "web"},
    ],
    "general_fact": [
        {"q": "{region} {place} {user_need_phrase}", "goal": "查公开网页事实", "source": "web"},
        {"q": "{place} {user_need_phrase}", "goal": "查地点相关事实", "source": "web"},
    ],
    "seasonal_operation_status": [
        {"q": "{place} 开放 通知 官方", "goal": "查季节性开放官方公告", "source": "official"},
        {"q": "{place} 闭园 公告", "goal": "查闭园/管制公告", "source": "official"},
        {"q": "{time} {place} 开放", "goal": "查当年/近期开放状态", "source": "official"},
        {"q": "site:gov.cn {place} 开放", "goal": "查政务网站开放通知", "source": "official"},
    ],
    "road_opening_period": [
        {"q": "{place} 通车 时间 官方", "goal": "查道路通车官方信息", "source": "official"},
        {"q": "{time} {place} 开放 通知", "goal": "查当年开放通知", "source": "official"},
        {"q": "{place} 交通管制 公告", "goal": "查交通管制公告", "source": "official"},
    ],
    "best_time_to_visit": [
        {"q": "{place} 几月份去 最好", "goal": "查最佳游玩月份", "source": "advisory"},
        {"q": "{place} 最佳旅游时间", "goal": "查季节建议", "source": "advisory"},
        {"q": "{region} {place} 季节 攻略", "goal": "查区域季节背景", "source": "advisory"},
    ],
    "crowd_level": [
        {"q": "{place} 人多吗 游客评价", "goal": "查拥挤程度体验信号", "source": "review"},
        {"q": "{place} 旺季 淡季 人流", "goal": "查淡旺季人流", "source": "review"},
        {"q": "{place} 大众点评 人多", "goal": "查点评平台拥挤反馈", "source": "review"},
    ],
    "review_summary": [
        {"q": "{place} 值得去吗 游客评价", "goal": "查总体游玩评价", "source": "review"},
        {"q": "{place} 避坑 游玩体验", "goal": "查负面/避坑体验", "source": "review"},
        {"q": "{place} 携程 游客评价", "goal": "查 OTA 评价信号", "source": "review"},
    ],
    "commercialization_risk": [
        {"q": "{place} 商业化严重吗 游客评价", "goal": "查商业化抱怨", "source": "review"},
        {"q": "{place} 宰客 避坑", "goal": "查宰客/坑人反馈", "source": "review"},
        {"q": "{place} 值不值得去", "goal": "查性价比评价", "source": "review"},
    ],
    "route_plan": [
        {"q": "{place} 怎么去 交通", "goal": "查到达交通方式", "source": "route"},
        {"q": "{city} {place} 自驾 公交", "goal": "查城际+市内交通", "source": "route"},
    ],
    "itinerary_feasibility": [
        {"q": "{place} 一天 够玩吗", "goal": "查一日游可行性体验", "source": "advisory"},
        {"q": "{origin} {place} 自驾 多久", "goal": "查路程时间背景", "source": "route"},
    ],
    "distance": [
        {"q": "{origin} {place} 距离 公里", "goal": "网页侧距离线索（路线以 baidu_route 为准）", "source": "route"},
    ],
    "open_advice": [
        {"q": "{place} {user_need_phrase}", "goal": "按用户原问法检索公开网页", "source": "public_web"},
        {"q": "{city} {place} {user_need_phrase}", "goal": "带城市限定检索", "source": "public_web"},
    ],
}

_INTENT_EXTRA_ANGLES: dict[str, list[dict]] = {
    PrimaryIntent.REALTIME_CHECK.value: [
        {"q": "{time} {place} 最新 通知", "goal": "查最新动态/通知", "source": "official"},
    ],
    PrimaryIntent.REVIEW_CHECK.value: [
        {"q": "{place} 大众点评 评价", "goal": "查点评平台体验", "source": "review"},
    ],
}

_DAY_NIGHT_RE = re.compile(r"白天|晚上|夜间|夜游|早晨|清晨", re.I)


@dataclass
class QueryRewriteSlots:
    anchor_entity: str
    city: str
    region: str
    country: str
    primary_intent: str
    claim_types: list[str]
    time_scope: str
    time_hint: str
    user_query: str
    user_need_phrase: str
    origin: str
    disambiguation_label: str
    anchor_keywords: list[str]

    @property
    def place(self) -> str:
        return self.anchor_entity


class SearchQueryRewriter:
    """Rule-based query understanding → multi-query rewrite (ChatGPT-style slots)."""

    def __init__(self, slots: QueryRewriteSlots, *, tried_queries: set[str] | None = None) -> None:
        self.slots = slots
        self.tried_queries = tried_queries or set()

    @classmethod
    def from_planning_context(
        cls,
        ctx: dict,
        state: TravelAgentState | None = None,
    ) -> SearchQueryRewriter:
        entities = ctx.get("entities") or {}
        place = (
            (entities.get("places") or [None])[0]
            or ctx.get("comparison_active_place")
            or "目的地"
        )
        frame = state.semantic_frame if state else None
        intent = state.intent_profile if state and state.intent_profile else None
        primary_intent = (
            intent.primary_intent.value
            if intent
            else str(ctx.get("primary_intent") or "lookup")
        )
        time_scope = ""
        if frame and frame.time_scope:
            time_scope = frame.time_scope.value
        elif ctx.get("user_need_residual"):
            time_scope = str((ctx["user_need_residual"] or {}).get("time_scope") or "")

        user_query = str(ctx.get("raw_query") or "")
        need_phrase = cls._extract_need_phrase(user_query, place)

        slots = QueryRewriteSlots(
            anchor_entity=str(place),
            city=str(entities.get("city") or ""),
            region=str(entities.get("region") or ""),
            country=str(entities.get("country") or ""),
            primary_intent=primary_intent,
            claim_types=list(ctx.get("claim_types") or []),
            time_scope=time_scope,
            time_hint=cls._time_hint(time_scope, user_query),
            user_query=user_query,
            user_need_phrase=need_phrase,
            origin=cls._default_origin(entities, user_query),
            disambiguation_label=str(ctx.get("disambiguated_place_label") or ""),
            anchor_keywords=list(ctx.get("anchor_keywords") or []),
        )
        tried = set(ctx.get("tried_search_queries") or [])
        return cls(slots, tried_queries=tried)

    @staticmethod
    def _time_hint(time_scope: str, user_query: str) -> str:
        if time_scope in {TimeScope.CURRENT.value, "current"} or re.search(
            r"今天|今日|现在|当前", user_query
        ):
            return "今天"
        if re.search(r"明天", user_query):
            return "明天"
        if re.search(r"今年|202\d", user_query):
            m = re.search(r"202\d", user_query)
            return m.group(0) if m else str(date.today().year)
        return str(date.today().year)

    @staticmethod
    def _extract_need_phrase(user_query: str, place: str) -> str:
        text = user_query.strip()
        if place and place in text:
            text = text.replace(place, "").strip()
        text = re.sub(r"[？?。！!]", "", text).strip()
        return text[:40] or "旅游信息"

    @staticmethod
    def _default_origin(entities: dict, user_query: str) -> str:
        region = str(entities.get("region") or "")
        if region in ("新疆", "Xinjiang") or "新疆" in user_query:
            return "乌鲁木齐市"
        city = str(entities.get("city") or "")
        return city

    def plan_items(self, *, max_items: int = 6) -> list[SearchQueryPlanItem]:
        claims = self._resolved_claims()
        items: list[SearchQueryPlanItem] = []
        seen_queries: set[str] = set(self.tried_queries)

        for claim in claims:
            for angle in self._angles_for_claim(claim):
                query = self._render(angle["q"])
                if not query or query in seen_queries:
                    continue
                seen_queries.add(query)
                anchors = self._anchor_keywords_for_query(query)
                items.append(
                    SearchQueryPlanItem(
                        anchor_entity=self.slots.place,
                        claim_type=claim,
                        search_goal=str(angle.get("goal") or f"查 {claim} 证据"),
                        search_query=query[:96],
                        information_need=claim,
                        preferred_tool=self._preferred_tool(claim, angle),
                        source_hint=str(angle.get("source") or ""),
                        time_hint=self.slots.time_hint if "{time}" in angle["q"] else "",
                        expected_source_types=self._expected_sources(angle.get("source")),
                        anchor_keywords=anchors,
                        tool_parameters=self._tool_parameters(claim),
                    )
                )
                if len(items) >= max_items:
                    return items

        if _DAY_NIGHT_RE.search(self.slots.user_query):
            for extra in self._day_night_angles():
                query = self._render(extra["q"])
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                items.append(
                    SearchQueryPlanItem(
                        anchor_entity=self.slots.place,
                        claim_type="visit_experience",
                        search_goal=extra["goal"],
                        search_query=query[:96],
                        information_need="review_summary",
                        source_hint="review",
                        anchor_keywords=self._anchor_keywords_for_query(query),
                    )
                )
                if len(items) >= max_items:
                    break
        return items

    def to_search_tasks(self, *, max_tasks: int = 3) -> list[SearchTask]:
        tasks: list[SearchTask] = []
        for item in self.plan_items(max_items=max_tasks):
            tasks.append(
                SearchTask(
                    task_id=f"rewrite-{uuid.uuid4().hex[:8]}",
                    lookup_intent=item.search_goal,
                    claim_target=item.claim_type,
                    anchor_keywords=item.anchor_keywords,
                    search_query=item.search_query,
                    information_need=item.information_need,
                    preferred_tool=item.preferred_tool,
                    tool_parameters=item.tool_parameters,
                    rationale=f"query_rewrite:{item.source_hint or 'web'}",
                )
            )
        return tasks

    def gap_query_templates(self, claim_type: str, *, max_queries: int = 4) -> list[str]:
        """Gap-fill: claim-specific queries (never claim_type.replace('_',' '))."""
        if claim_type == "general_travel_advice":
            inferred = self._infer_claim_from_query()
            effective = inferred if inferred != "open_advice" else claim_type
        else:
            effective = claim_type
        single = QueryRewriteSlots(
            anchor_entity=self.slots.anchor_entity,
            city=self.slots.city,
            region=self.slots.region,
            country=self.slots.country,
            primary_intent=self.slots.primary_intent,
            claim_types=[effective],
            time_scope=self.slots.time_scope,
            time_hint=self.slots.time_hint,
            user_query=self.slots.user_query,
            user_need_phrase=self.slots.user_need_phrase,
            origin=self.slots.origin,
            disambiguation_label=self.slots.disambiguation_label,
            anchor_keywords=self.slots.anchor_keywords,
        )
        sub = SearchQueryRewriter(single, tried_queries=self.tried_queries)
        return [i.search_query for i in sub.plan_items(max_items=max_queries)]

    def slots_summary(self) -> dict:
        return {
            "anchor_entity": self.slots.place,
            "city": self.slots.city,
            "region": self.slots.region,
            "primary_intent": self.slots.primary_intent,
            "claim_types": self._resolved_claims(),
            "time_hint": self.slots.time_hint,
            "user_need_phrase": self.slots.user_need_phrase,
            "disambiguation_label": self.slots.disambiguation_label,
        }

    def _resolved_claims(self) -> list[str]:
        claims: list[str] = []
        for raw in self.slots.claim_types:
            if raw == "general_travel_advice":
                inferred = self._infer_claim_from_query()
                norm = inferred if inferred != "open_advice" else "open_advice"
            else:
                norm = _CLAIM_ALIASES.get(raw, raw)
            if norm not in claims:
                claims.append(norm)
        if not claims:
            claims.append(self._infer_claim_from_query())
        return claims

    def _infer_claim_from_query(self) -> str:
        q = self.slots.user_query
        if re.search(r"海拔|高度.*米|多高", q):
            return "elevation"
        if re.search(r"门票|票价|收费|免费", q):
            return "ticket_price"
        if re.search(r"几点|开放时间|营业时间|关门", q):
            return "opening_hours"
        if re.search(r"值得|好不好|避坑|商业化", q):
            return "review_summary"
        if re.search(r"一天|一日游|够玩", q):
            return "itinerary_feasibility"
        if self.slots.primary_intent == PrimaryIntent.REALTIME_CHECK.value:
            return "seasonal_operation_status"
        return "open_advice"

    def _angles_for_claim(self, claim: str) -> list[dict]:
        norm = _CLAIM_ALIASES.get(claim, claim)
        angles = list(_CLAIM_QUERY_ANGLES.get(norm, _CLAIM_QUERY_ANGLES.get("open_advice", [])))
        extras = _INTENT_EXTRA_ANGLES.get(self.slots.primary_intent, [])
        if self.slots.primary_intent == PrimaryIntent.LOOKUP.value and norm in {
            "ticket_price",
            "opening_hours",
            "elevation",
            "seasonal_operation_status",
        }:
            extras = []
        merged = angles + [e for e in extras if e not in angles]
        return merged

    def _day_night_angles(self) -> list[dict]:
        place = self.slots.place
        return [
            {"q": f"{place} 白天 晚上 哪个好玩", "goal": "比较白天/夜晚游玩体验"},
            {"q": f"{place} 夜游 游客评价", "goal": "查夜间游玩评价"},
            {"q": f"{place} 晚上 开放时间", "goal": "查夜间开放/照明信息"},
            {"q": f"{place} 白天 拍照 游玩体验", "goal": "查白天体验信号"},
        ]

    def _render(self, template: str) -> str:
        s = self.slots
        place = s.disambiguation_label or s.place
        mapping = {
            "place": place,
            "city": s.city,
            "region": s.region,
            "time": s.time_hint,
            "origin": s.origin,
            "user_need_phrase": s.user_need_phrase,
        }
        try:
            out = template.format(**mapping)
        except KeyError:
            return ""
        out = re.sub(r"\s+", " ", out).strip()
        # Drop empty slot tokens like leading city when missing
        out = re.sub(r"^\s+", "", out)
        if not place or place == "目的地":
            return ""
        return out

    def _anchor_keywords_for_query(self, query: str) -> list[str]:
        anchors = list(self.slots.anchor_keywords)
        place = self.slots.place
        if place and place not in anchors:
            anchors.insert(0, place)
        if self.slots.city and self.slots.city not in anchors:
            anchors.append(self.slots.city)
        # Keep anchors that appear in query or are the place
        return [a for a in anchors if len(a) >= 2 and (a in query or a == place)][:6] or [place]

    @staticmethod
    def _preferred_tool(claim: str, angle: dict) -> str:
        if (
            claim in {"route_plan", "distance", "itinerary_feasibility"}
            and angle.get("source") == "route"
            and "{origin}" in str(angle.get("q") or "")
        ):
            return "baidu_route_mcp"
        return "search_mcp"

    @staticmethod
    def _expected_sources(source_hint: str | None) -> list[str]:
        return {
            "official": ["official", "public_web", "tourism_board"],
            "review": ["review", "public_web", "travel_note"],
            "web": ["public_web", "search_result"],
            "encyclopedia": ["encyclopedia", "public_web", "map"],
            "route": ["map", "public_web"],
            "advisory": ["public_web", "travel_note"],
        }.get(source_hint or "", ["public_web"])

    def _tool_parameters(self, claim: str) -> dict[str, str]:
        if claim not in {"route_plan", "distance", "itinerary_feasibility"}:
            return {}
        origin = self.slots.origin
        dest = self.slots.place
        if not origin or not dest:
            return {}
        return {"origin": origin, "destination": dest, "mode": "driving"}
