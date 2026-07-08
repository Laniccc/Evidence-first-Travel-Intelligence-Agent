"""Generate LookupQueryObjective from state — no per-place query tables."""

from __future__ import annotations

from app.orchestrator.fact_lookup_policy import is_ticket_claim_type
from app.orchestrator.fact_lookup_anchor_policy import raw_place_label, resolved_place_label
from app.orchestrator.fact_lookup_policy import fact_need_label, is_geographic_fact_need
from app.orchestrator.lookup_research_chain import ensure_lookup_chain_initialized, get_lookup_chain
from app.schemas.lookup_research_chain import LookupQueryObjective, SourceFamily
from app.schemas.user_query import TravelAgentState


def _anchor_terms(state: TravelAgentState) -> list[str]:
    place = resolved_place_label(state) or raw_place_label(state)
    terms = [place] if place else []
    frame = state.semantic_frame
    if frame and frame.entities:
        if frame.entities.city and frame.entities.city not in terms:
            terms.append(frame.entities.city)
    return [t for t in terms if t][:4]


def _must_include_for_need(need: str) -> list[str]:
    label = fact_need_label(need)
    if need == "ticket_price":
        return [label, "官方"]
    if need == "elevation":
        return [label]
    if need in {"opening_hours", "reservation_policy"}:
        return [label]
    return [label]


def _avoid_for_need(need: str) -> list[str]:
    if is_ticket_claim_type(need) or need == "ticket_price":
        return ["攻略软文", "未经核实的二手转述"]
    if need == "elevation":
        return ["攻略软文中的未经核实数值"]
    return ["model prior", "knowledge_prior"]


def _ticket_multi_query_objectives(
    state: TravelAgentState,
    need: str,
    source_family: SourceFamily,
    *,
    anchors: list[str],
    label: str,
    must: list[str],
    avoid: list[str],
    max_objectives: int,
) -> list[LookupQueryObjective]:
    from app.orchestrator.ticket_price_query_ladder import build_ticket_price_escalation_queries
    from app.orchestrator.ticket_product_policy import ensure_ticket_product_context, ticket_product_keywords

    ensure_ticket_product_context(state)
    place = resolved_place_label(state) or (anchors[0] if anchors else "")
    product_kws = ticket_product_keywords(state)
    tier_by_family = {
        "official_operator": {"official", "announcement"},
        "ticket_platform": {"ticket_platform"},
        "government_tourism": {"official", "announcement"},
        "web_reference": {"scenic_alias", "ticket_office", "announcement", "official"},
    }
    allowed_tiers = tier_by_family.get(source_family, {"official", "ticket_platform", "scenic_alias"})
    pairs = [
        (tier, q)
        for tier, q in build_ticket_price_escalation_queries(state, max_queries=max_objectives * 3)
        if tier in allowed_tiers
    ]
    prefix = {
        "ticket_platform": "platform",
        "official_operator": "official",
        "government_tourism": "gov",
        "web_reference": "web",
    }.get(source_family, "ticket")
    objectives: list[LookupQueryObjective] = []
    for tier, q in pairs:
        objectives.append(
            LookupQueryObjective(
                objective=f"{prefix}_{tier}_{need}_{abs(hash(q)) % 10_000}",
                source_family=source_family,
                query_intent=f"检索{place}{label}（{tier}/{source_family}）",
                anchor_terms=[place] if place else anchors[:2],
                must_include=product_kws[:4] or must,
                avoid_as_final=avoid,
                search_query=q,
            )
        )
    return objectives[:max_objectives]


def build_lookup_query_objectives(
    state: TravelAgentState,
    need: str,
    source_family: SourceFamily,
    *,
    max_objectives: int = 3,
) -> list[LookupQueryObjective]:
    ensure_lookup_chain_initialized(state)
    anchors = _anchor_terms(state)
    label = fact_need_label(need)
    must = _must_include_for_need(need)
    avoid = _avoid_for_need(need)
    objectives: list[LookupQueryObjective] = []

    if is_ticket_claim_type(need) and source_family in {
        "ticket_platform",
        "official_operator",
        "government_tourism",
        "web_reference",
    }:
        ticket_objs = _ticket_multi_query_objectives(
            state,
            need,
            source_family,
            anchors=anchors,
            label=label,
            must=must,
            avoid=avoid,
            max_objectives=max_objectives,
        )
        if ticket_objs:
            chain = get_lookup_chain(state)
            if chain.query_objectives:
                existing = {o.signature() for o in chain.query_objectives}
                ticket_objs = [o for o in ticket_objs if o.signature() not in existing]
            return ticket_objs[:max_objectives]

    if source_family == "official_operator":
        objectives.append(
            LookupQueryObjective(
                objective=f"official_{need}",
                source_family=source_family,
                query_intent=f"查找景区/运营方关于{label}的官方说明",
                anchor_terms=anchors,
                must_include=must,
                avoid_as_final=avoid,
            )
        )
    elif source_family == "government_tourism":
        objectives.append(
            LookupQueryObjective(
                objective=f"gov_{need}",
                source_family=source_family,
                query_intent=f"查找政府/文旅部门关于{label}的公告",
                anchor_terms=anchors,
                must_include=must,
                avoid_as_final=avoid,
            )
        )
    elif source_family == "geo_authority":
        elev_terms = (
            [label, "海拔", "altitude", "elevation", "最高峰", "主峰"]
            if need == "elevation"
            else must
        )
        objectives.append(
            LookupQueryObjective(
                objective=f"geo_{need}",
                source_family=source_family,
                query_intent=f"查找权威地理/百科数据源中的{label}数值",
                anchor_terms=anchors,
                must_include=elev_terms,
                avoid_as_final=avoid,
            )
        )
        if is_geographic_fact_need(need):
            objectives.append(
                LookupQueryObjective(
                    objective=f"geo_crosscheck_{need}",
                    source_family=source_family,
                    query_intent=f"用第二地理数据源交叉验证{label}",
                    anchor_terms=anchors,
                    must_include=must,
                    avoid_as_final=avoid,
                )
            )
    elif source_family == "map_candidate":
        objectives.append(
            LookupQueryObjective(
                objective=f"map_{need}",
                source_family=source_family,
                query_intent=f"查找地图 POI 上的{label}候选字段",
                anchor_terms=anchors,
                must_include=must,
                avoid_as_final=["作为官方终证"],
            )
        )
    else:
        objectives.append(
            LookupQueryObjective(
                objective=f"web_{need}",
                source_family="web_reference",
                query_intent=f"查找公开网页中对{label}的引用（仅作线索）",
                anchor_terms=anchors,
                must_include=must,
                avoid_as_final=avoid,
            )
        )

    chain = get_lookup_chain(state)
    if chain.query_objectives:
        existing = {o.signature() for o in chain.query_objectives}
        objectives = [o for o in objectives if o.signature() not in existing]
    return objectives[:max_objectives]


def build_peak_elevation_objectives(
    state: TravelAgentState,
    *,
    place: str,
    peak_names: list[str],
    max_objectives: int = 4,
) -> list[LookupQueryObjective]:
    from app.orchestrator.peak_elevation_extraction import discover_peak_names_from_evidence

    anchors = _anchor_terms(state)
    if place and place not in anchors:
        anchors = [place, *anchors]
    names = list(peak_names)
    if not names:
        names = discover_peak_names_from_evidence(list(state.evidence or []))
    objectives: list[LookupQueryObjective] = [
        LookupQueryObjective(
            objective="highest_peak_elevation",
            source_family="geo_authority",
            query_intent=f"查找{place or anchors[0]}最高峰及其海拔米数",
            anchor_terms=anchors,
            must_include=["最高峰", "海拔"],
            avoid_as_final=["仅范围描述"],
        ),
        LookupQueryObjective(
            objective="main_peaks_overview",
            source_family="web_reference",
            query_intent=f"查找{place or anchors[0]}主要山峰/主峰海拔列表",
            anchor_terms=anchors,
            must_include=["主峰", "海拔"],
            avoid_as_final=["model prior"],
        ),
    ]
    for peak in names[:max_objectives]:
        objectives.append(
            LookupQueryObjective(
                objective=f"peak_{peak}",
                source_family="geo_authority",
                query_intent=f"查找{peak}的具体海拔米数",
                anchor_terms=[*anchors[:1], peak],
                must_include=[peak, "海拔"],
                avoid_as_final=["攻略软文"],
            )
        )
    return objectives[: max_objectives + 2]


def objective_to_search_query(objective: LookupQueryObjective) -> str:
    if objective.search_query and objective.search_query.strip():
        return objective.search_query.strip()[:120]
    parts: list[str] = []
    parts.extend(objective.anchor_terms[:2])
    parts.extend(objective.must_include[:2])
    if objective.query_intent:
        intent = objective.query_intent
        for token in ("查找", "关于", "的", "官方说明", "公告", "候选", "信号", "数值", "引用"):
            intent = intent.replace(token, " ")
        intent = " ".join(intent.split())
        if intent:
            parts.append(intent[:40])
    return " ".join(dict.fromkeys(p for p in parts if p))[:120]


def objectives_from_gap(
    *,
    claim_type: str,
    source_family: SourceFamily | None,
    anchor_terms: list[str],
    query_intent: str,
) -> LookupQueryObjective:
    return LookupQueryObjective(
        objective=f"gap_{claim_type}",
        source_family=source_family or "web_reference",
        query_intent=query_intent,
        anchor_terms=anchor_terms[:4],
        must_include=[fact_need_label(claim_type)] if claim_type else [],
        avoid_as_final=["knowledge_prior", "model prior"],
    )
