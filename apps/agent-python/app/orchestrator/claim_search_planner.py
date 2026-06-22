"""Build targeted web-search queries from ResponseContract + SemanticFrame."""

from __future__ import annotations

import re
from datetime import date

from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState

_ADMIN_REGION_IN_TEXT = re.compile(
    r"新疆|西藏|内蒙古|广西|宁夏|香港|澳门|台湾"
    r"|黑龙江|吉林|辽宁|河北|山西|陕西|甘肃|青海|山东|河南|江苏|浙江|安徽|福建|江西|湖北|湖南|广东|海南|四川|贵州|云南"
    r"|北京|上海|天津|重庆"
    r"|[^，,、\s]{2,8}(?:省|自治区|特别行政区)",
    re.I,
)

_NO_HITS = re.compile(r"No search hits|无结果|returned no results", re.I)

# Well-known aliases / route codes for finer retrieval
_ROAD_QUERY_HINTS: dict[str, list[str]] = {
    "独库公路": ["G217", "独山子", "库车", "天山公路"],
}


class ClaimSearchPlanner:
    """Claim-aware search query templates for S5."""

    @classmethod
    def max_search_attempts(cls, state: TravelAgentState) -> int:
        contract = state.response_contract
        if contract and any(
            c.priority == "required" and not c.model_prior_allowed
            for c in contract.claim_requirements
        ):
            return 6
        return 3

    @classmethod
    def build_queries(cls, state: TravelAgentState) -> list[str]:
        frame = state.semantic_frame
        contract = state.response_contract
        raw = (state.raw_user_query or "").strip()
        if not raw and not frame:
            return []

        place = None
        region = ""
        city = ""
        if frame and frame.entities:
            place = frame.entities.places[0] if frame.entities.places else None
            region = (frame.entities.region or "").strip()
            city = (frame.entities.city or "").strip()

        if not region:
            region = cls._region_from_text(raw)

        claim_types = (
            [c.claim_type for c in contract.claim_requirements]
            if contract
            else (list(frame.information_needs) if frame else [])
        )

        queries: list[str] = []
        if "seasonal_operation_status" in claim_types:
            queries.extend(cls._seasonal_operation_queries(place, region, city, raw))
        elif any(c in claim_types for c in ("opening_hours", "ticket_price")):
            label = place or city or raw[:40]
            queries.extend(
                [
                    f"{label} {claim_types[0]}".strip(),
                    f"{label} {region} 官方".strip(),
                    f"{label} 门票 价格" if "ticket" in claim_types[0] else f"{label} 开放时间",
                ]
            )

        if not queries:
            queries = [raw]

        return cls._dedupe(queries)

    @classmethod
    def refine_queries_after_misses(
        cls,
        state: TravelAgentState,
        tried: set[str] | None = None,
    ) -> list[str]:
        """Shorter fallback queries when prior searches returned no hits."""
        frame = state.semantic_frame
        if tried is None:
            tried = cls._tried_from_traces(state)

        place = ""
        region = ""
        if frame and frame.entities:
            place = (frame.entities.places[0] if frame.entities.places else "") or ""
            region = (frame.entities.region or "").strip()
        raw = state.raw_user_query or ""
        if not region:
            region = cls._region_from_text(raw)

        year = date.today().year
        label = place or "目的地"
        short = [
            f"{label}开放时间",
            f"{label}几月通车",
            f"{label}{year}通车",
            f"{label}封路通知",
        ]
        if region:
            short.append(f"{region}{label}开放")
        if "独库" in label or "独库" in raw:
            short.extend(
                [
                    "独库公路开放时间",
                    "独库公路几月通车",
                    f"独库公路{year}",
                    "G217独库公路通车",
                ]
            )
        for hint in _ROAD_QUERY_HINTS.get(place, []):
            short.append(f"{label}{hint}通车")

        return cls._dedupe(q for q in short if q not in tried)

    @classmethod
    def resolve_query_list(cls, state: TravelAgentState, prompt_context: dict) -> list[str]:
        queries = prompt_context.get("claim_search_queries")
        if queries is None:
            queries = cls.build_queries(state)
            prompt_context["claim_search_queries"] = queries
        return list(queries)

    @classmethod
    def primary_information_need(cls, state: TravelAgentState) -> str | None:
        contract = state.response_contract
        if contract:
            for claim in contract.claim_requirements:
                if claim.priority == "required":
                    return claim.claim_type
        frame = state.semantic_frame
        if frame and frame.information_needs:
            return frame.information_needs[0]
        return None

    @staticmethod
    def _region_from_text(text: str) -> str:
        match = _ADMIN_REGION_IN_TEXT.search(text)
        return match.group(0) if match else ""

    @staticmethod
    def _dedupe(queries) -> list[str]:
        return list(dict.fromkeys(q for q in queries if q and str(q).strip()))

    @staticmethod
    def _tried_from_traces(state: TravelAgentState) -> set[str]:
        tried: set[str] = set()
        for trace in state.tool_traces:
            if trace.tool_name != "search_mcp":
                continue
            q = (trace.input or {}).get("query")
            if q:
                tried.add(str(q).strip())
        return tried

    @staticmethod
    def _searches_failed(state: TravelAgentState) -> bool:
        for ev in state.evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                if _NO_HITS.search(str(claim.value)):
                    return True
        return False

    @staticmethod
    def _seasonal_operation_queries(
        place: str | None,
        region: str,
        city: str,
        raw: str,
    ) -> list[str]:
        label = place or "公路"
        year = date.today().year
        loc = " ".join(x for x in (region, city) if x).strip()
        blob = f"{raw} {region} {city}"

        # Tier 1 — short, search-engine friendly (try first)
        queries = [
            f"{label}什么时候开放",
            f"{label}几月通车",
            f"{label}{year}通车时间",
        ]
        # Tier 2 — official / regional
        if "新疆" in blob:
            queries.extend(
                [
                    f"新疆交通运输厅 {label} 通车",
                    f"{label} 新疆 封闭通告",
                    f"独库公路 {year} 通车公告",
                ]
            )
        else:
            queries.append(f"{label} {loc} 交通运输厅 通车".strip())
        # Tier 3 — route / compound
        queries.extend(
            [
                f"{label} {loc} 开放月份 官方".strip(),
                f"G217 {label} 开放时间" if "独库" in label else f"{label} 公路 开放 公告",
            ]
        )
        for hint in _ROAD_QUERY_HINTS.get(label, []):
            queries.append(f"{label} {hint} 通车时间")
        return queries
