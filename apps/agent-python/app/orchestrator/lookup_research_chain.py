"""LookupResearchChain helpers — phase order, state R/W, audit, dedup."""

from __future__ import annotations

import hashlib

from app.orchestrator.fact_lookup_anchor_policy import (
    needs_geo_anchor,
    raw_place_label,
    resolved_place_label,
)
from app.orchestrator.fact_lookup_policy import (
    count_actionable_fact_claims,
    fact_need_label,
    has_official_fact_evidence,
    is_fact_lookup_task,
    is_geographic_fact_need,
    primary_fact_need_from_state,
)
from app.schemas.lookup_research_chain import (
    LookupPhase,
    LookupQueryObjective,
    LookupResearchChainState,
    LookupResearchFrame,
    LookupTargetEntity,
    RetrievalAudit,
    SourceFamily,
    SourcePlanItem,
)
from app.schemas.user_query import TravelAgentState


_PHASE_ORDER_BY_NEED: dict[str, list[LookupPhase]] = {
    "ticket_price": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_site_discovery",
        "official_ticket_page_discovery",
        "platform_ticket_candidate",
        "ticket_price_extraction",
        "retrieval_audit",
    ],
    "opening_hours": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_discovery",
        "fact_acquisition",
        "retrieval_audit",
    ],
    "reservation_policy": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_discovery",
        "fact_acquisition",
        "retrieval_audit",
    ],
    "seasonal_operation_status": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_discovery",
        "fact_acquisition",
        "retrieval_audit",
    ],
    "elevation": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_discovery",
        "fact_acquisition",
        "peak_elevation_lookup",
        "retrieval_audit",
    ],
    "general_fact": [
        "research_frame",
        "entity_anchor",
        "source_plan",
        "official_discovery",
        "fact_acquisition",
        "retrieval_audit",
    ],
}

_SOURCE_PLAN_BY_NEED: dict[str, list[SourcePlanItem]] = {
    "ticket_price": [
        SourcePlanItem(
            source_family="official_operator",
            purpose="景区运营方官网/游客服务的票价或免费政策",
            tool_candidates=[
                "official_source_discovery_mcp",
                "search_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
            ],
        ),
        SourcePlanItem(
            source_family="government_tourism",
            purpose="文旅/政府公告中的票务政策",
            tool_candidates=["search_mcp", "official_page_reader_mcp"],
        ),
        SourcePlanItem(
            source_family="ticket_platform",
            purpose="授权票务平台的候选价信号",
            tool_candidates=[
                "fliggy_ticket_api_mcp",
                "ticketlens_experience_mcp",
                "ctrip_ticket_signal_crawler_mcp",
                "dianping_ticket_signal_crawler_mcp",
                "baidu_place_detail_mcp",
            ],
        ),
    ],
    "opening_hours": [
        SourcePlanItem(
            source_family="official_operator",
            purpose="官方开放时间/营业时间",
            tool_candidates=[
                "official_source_discovery_mcp",
                "official_page_reader_mcp",
                "search_mcp",
            ],
        ),
        SourcePlanItem(
            source_family="map_candidate",
            purpose="地图 POI 营业时间候选",
            tool_candidates=["baidu_place_detail_mcp", "search_mcp"],
        ),
    ],
    "elevation": [
        SourcePlanItem(
            source_family="geo_authority",
            purpose="百科/地理数据源的数值海拔",
            tool_candidates=["wikidata_mcp", "wikipedia_mcp", "osm_mcp"],
        ),
        SourcePlanItem(
            source_family="official_operator",
            purpose="景区/管理方页面的地理说明",
            tool_candidates=["official_source_discovery_mcp", "official_page_reader_mcp", "search_mcp"],
        ),
        SourcePlanItem(
            source_family="web_reference",
            purpose="交叉验证的公开参考",
            tool_candidates=["search_mcp"],
        ),
    ],
}

_FORBIDDEN_SHORTCUTS = [
    "knowledge_prior",
    "dianping_review_crawler_mcp for ticket_price/opening_hours as strong evidence",
    "model prior for hard facts",
]


def lookup_phase_order(need: str) -> list[LookupPhase]:
    return list(_PHASE_ORDER_BY_NEED.get(need, _PHASE_ORDER_BY_NEED["general_fact"]))


def get_lookup_chain(state: TravelAgentState) -> LookupResearchChainState:
    structured = state.structured_result or {}
    raw = structured.get("lookup_research_chain")
    if isinstance(raw, dict):
        return LookupResearchChainState.model_validate(raw)
    if isinstance(raw, LookupResearchChainState):
        return raw
    return LookupResearchChainState()


def save_lookup_chain(state: TravelAgentState, chain: LookupResearchChainState) -> None:
    structured = dict(state.structured_result or {})
    structured["lookup_research_chain"] = chain.model_dump()
    state.structured_result = structured


def ensure_lookup_chain_initialized(state: TravelAgentState) -> LookupResearchChainState:
    if not is_fact_lookup_task(state):
        return get_lookup_chain(state)
    chain = get_lookup_chain(state)
    if chain.frame and chain.frame.lookup_goal:
        return chain
    need = primary_fact_need_from_state(state)
    frame = state.semantic_frame
    place = raw_place_label(state)
    entity = LookupTargetEntity(
        raw_name=place,
        resolved_name=resolved_place_label(state) if resolved_place_label(state) != place else None,
        city=(frame.entities.city if frame and frame.entities else None),
        province=(frame.entities.region if frame and frame.entities else None),
        country=(frame.entities.country if frame and frame.entities else None) or "China",
    )
    label = fact_need_label(need)
    chain.frame = LookupResearchFrame(
        lookup_goal=f"确认{place}的{label}",
        primary_fact_need=need,
        target_entity=entity,
        source_hypotheses=_default_source_hypotheses(need),
        research_questions=_default_research_questions(need, place),
    )
    chain.source_plan = list(_SOURCE_PLAN_BY_NEED.get(need, _SOURCE_PLAN_BY_NEED.get("general_fact", [])))
    if not chain.source_plan:
        chain.source_plan = [
            SourcePlanItem(
                source_family="web_reference",
                purpose=f"检索{label}相关公开信息",
                tool_candidates=["search_mcp", "official_source_discovery_mcp"],
            )
        ]
    chain.current_phase = "research_frame"
    if "research_frame" not in chain.completed_phases:
        chain.completed_phases.extend(["research_frame", "source_plan"])
        chain.current_phase = "entity_anchor"
    save_lookup_chain(state, chain)
    return chain


def _default_source_hypotheses(need: str) -> list[str]:
    if need == "ticket_price":
        return [
            "景区运营官网可能公布票价或免费政策",
            "政府/文旅公告可能说明票务政策",
            "OTA 平台可能提供候选价但非官方终证",
        ]
    if need == "elevation":
        return [
            "百科/地理数据源可能提供海拔数值",
            "景区官网可能描述山体高度",
            "第三方攻略仅作线索，不可当作终证",
        ]
    return ["官方来源优先", "第三方来源仅作候选线索"]


def _default_research_questions(need: str, place: str) -> list[str]:
    label = fact_need_label(need)
    return [
        f"「{place}」是否已锚定为唯一实体？",
        f"是否存在可支持{label}的官方或权威来源？",
        f"第三方线索是否与官方口径冲突？",
    ]


def next_recommended_phase(state: TravelAgentState) -> LookupPhase | None:
    chain = ensure_lookup_chain_initialized(state)
    need = primary_fact_need_from_state(state)
    order = lookup_phase_order(need)
    completed = set(chain.completed_phases)
    for phase in order:
        if phase in completed:
            continue
        if phase == "entity_anchor" and not needs_geo_anchor(state) and _entity_anchored(state):
            mark_phase_complete(state, "entity_anchor")
            completed.add("entity_anchor")
            continue
        if phase == "peak_elevation_lookup":
            from app.orchestrator.peak_elevation_extraction import (
                elevation_needs_peak_gap,
                extract_peak_elevation_table,
            )
            from app.orchestrator.fact_lookup_anchor_policy import resolved_place_label

            table = extract_peak_elevation_table(
                list(state.evidence or []),
                place_name=resolved_place_label(state),
            )
            if not elevation_needs_peak_gap(table, exact_required=True):
                mark_phase_complete(state, "peak_elevation_lookup")
                completed.add("peak_elevation_lookup")
                continue
        return phase
    return None


def _entity_anchored(state: TravelAgentState) -> bool:
    structured = state.structured_result or {}
    if structured.get("fact_anchor"):
        return True
    frame = state.semantic_frame
    if frame and frame.entities and (frame.entities.city or frame.entities.region):
        return True
    return False


def mark_phase_complete(state: TravelAgentState, phase: LookupPhase) -> None:
    chain = get_lookup_chain(state)
    if phase not in chain.completed_phases:
        chain.completed_phases.append(phase)
    order = lookup_phase_order(primary_fact_need_from_state(state))
    if phase in order:
        idx = order.index(phase)
        if idx + 1 < len(order):
            chain.current_phase = order[idx + 1]
        else:
            chain.current_phase = "retrieval_audit"
    save_lookup_chain(state, chain)


def merge_chain_updates(state: TravelAgentState, updates: dict | None) -> None:
    if not updates:
        return
    chain = ensure_lookup_chain_initialized(state)
    if updates.get("frame"):
        data = updates["frame"]
        if isinstance(data, dict):
            chain.frame = LookupResearchFrame.model_validate({**(chain.frame.model_dump() if chain.frame else {}), **data})
    if updates.get("source_plan"):
        chain.source_plan = [SourcePlanItem.model_validate(x) for x in updates["source_plan"]]
    if updates.get("query_objectives"):
        chain.query_objectives = [LookupQueryObjective.model_validate(x) for x in updates["query_objectives"]]
    if updates.get("audit"):
        chain.audit = RetrievalAudit.model_validate(updates["audit"])
    if updates.get("completed_phase"):
        mark_phase_complete(state, updates["completed_phase"])
        chain = get_lookup_chain(state)
    save_lookup_chain(state, chain)


def build_retrieval_audit(state: TravelAgentState) -> RetrievalAudit:
    need = primary_fact_need_from_state(state)
    evidence = list(state.evidence or [])
    actionable = count_actionable_fact_claims(evidence, need) >= 1
    official = has_official_fact_evidence(evidence, need)
    audit = RetrievalAudit(
        entity_anchored=_entity_anchored(state),
        official_source_attempted=_official_attempted(state),
        official_fact_found=official,
        platform_candidate_found=_platform_candidate_found(evidence, need),
        conflict_possible=_conflict_possible(state),
    )
    if official and actionable:
        audit.recommended_next = "finish"
    elif need == "elevation":
        from app.orchestrator.peak_elevation_extraction import (
            elevation_needs_peak_gap,
            extract_peak_elevation_table,
        )

        table = extract_peak_elevation_table(evidence, place_name=resolved_place_label(state))
        structured = state.structured_result or {}
        if isinstance(structured.get("peak_elevation_table"), dict):
            table = extract_peak_elevation_table(evidence, place_name=resolved_place_label(state))
        if elevation_needs_peak_gap(table, exact_required=True):
            audit.recommended_next = "continue"
        elif actionable and not official:
            audit.recommended_next = "gap_fill"
        elif actionable:
            audit.recommended_next = "finish"
        elif _entity_anchored(state):
            audit.recommended_next = "continue"
    elif actionable and not official:
        audit.recommended_next = "gap_fill"
    elif _entity_anchored(state) and not actionable:
        audit.recommended_next = "continue"
    else:
        audit.recommended_next = "continue"
    chain = get_lookup_chain(state)
    chain.audit = audit
    save_lookup_chain(state, chain)
    return audit


def _official_attempted(state: TravelAgentState) -> bool:
    for t in state.tool_traces or []:
        name = str(t.tool_name or "")
        if any(x in name for x in ("official", "discovery", "reader")):
            return True
    return False


def _platform_candidate_found(evidence: list, need: str) -> bool:
    if need != "ticket_price":
        return False
    for ev in evidence:
        name = str(getattr(ev, "source_name", "") or "").lower()
        if any(x in name for x in ("ctrip", "dianping", "ticket", "携程", "点评", "fliggy", "飞猪", "ticketlens")):
            return True
    return False


def _conflict_possible(state: TravelAgentState) -> bool:
    structured = state.structured_result or {}
    return bool(structured.get("conflict_notes"))


def lookup_attempt_signature(
    *,
    subagent: str,
    claim_type: str,
    phase: str,
    source_family: str,
    objective: str,
) -> str:
    raw = f"{subagent}|{claim_type}|{phase}|{source_family}|{objective}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_duplicate_lookup_attempt(state: TravelAgentState, signature: str) -> bool:
    chain = get_lookup_chain(state)
    return signature in chain.attempt_signatures


def record_lookup_attempt(state: TravelAgentState, signature: str) -> None:
    chain = get_lookup_chain(state)
    if signature not in chain.attempt_signatures:
        chain.attempt_signatures.append(signature)
        chain.attempt_signatures = chain.attempt_signatures[-32:]
    save_lookup_chain(state, chain)


def advance_entity_anchor_if_satisfied(state: TravelAgentState) -> bool:
    """Mark entity_anchor complete when canonical place is already known."""
    from app.orchestrator.lookup_entity_resolution_policy import lookup_entity_anchor_satisfied

    if not is_fact_lookup_task(state) or not lookup_entity_anchor_satisfied(state):
        return False
    chain = get_lookup_chain(state)
    if "entity_anchor" in chain.completed_phases:
        return False
    mark_phase_complete(state, "entity_anchor")
    return True


def lookup_mandatory_entity_anchor(state: TravelAgentState, step: int) -> bool:
    from app.orchestrator.lookup_entity_resolution_policy import (
        entity_resolution_allowed_for_lookup,
        lookup_entity_anchor_satisfied,
    )

    if not is_fact_lookup_task(state) or step >= 6:
        return False
    if lookup_entity_anchor_satisfied(state):
        advance_entity_anchor_if_satisfied(state)
        return False
    if not entity_resolution_allowed_for_lookup(state):
        advance_entity_anchor_if_satisfied(state)
        return False
    chain = ensure_lookup_chain_initialized(state)
    return "entity_anchor" not in chain.completed_phases


def build_lookup_research_context(state: TravelAgentState) -> dict:
    if not is_fact_lookup_task(state):
        return {}
    chain = ensure_lookup_chain_initialized(state)
    need = primary_fact_need_from_state(state)
    nxt = next_recommended_phase(state)
    audit = chain.audit or build_retrieval_audit(state)
    return {
        "lookup_research_chain": chain.model_dump(),
        "lookup_phase_order": lookup_phase_order(need),
        "current_phase": chain.current_phase,
        "next_recommended_phase": nxt,
        "completed_phases": chain.completed_phases,
        "retrieval_audit": audit.model_dump(),
        "finish_conditions": [
            "coverage_report.all_required_covered",
            "retrieval_audit.recommended_next == finish",
            "step budget exhausted",
        ],
        "forbidden_shortcuts": _FORBIDDEN_SHORTCUTS,
    }


def source_families_for_phase(phase: LookupPhase, need: str) -> list[SourceFamily]:
    plan = _SOURCE_PLAN_BY_NEED.get(need, [])
    if phase in {"official_discovery", "official_site_discovery"}:
        return [p.source_family for p in plan if p.source_family in ("official_operator", "government_tourism")]
    if phase == "official_ticket_page_discovery":
        return ["official_operator"]
    if phase == "platform_ticket_candidate":
        return ["ticket_platform"]
    if phase == "ticket_price_extraction":
        return ["ticket_platform", "web_reference"]
    if phase == "peak_elevation_lookup":
        return ["geo_authority", "web_reference"]
    if phase == "fact_acquisition":
        if is_geographic_fact_need(need):
            return ["geo_authority", "web_reference"]
        return [p.source_family for p in plan if p.source_family not in ("official_operator", "government_tourism")]
    return []
