"""Normalize LLM JSON payloads into NormalizedUserRequest-compatible dicts."""

from __future__ import annotations

from typing import Any


_ENTITY_TYPE_ALIASES = {
    "place": "attraction",
    "poi": "attraction",
    "spot": "attraction",
    "scenic": "attraction",
    "scenic_spot": "attraction",
    "lake": "natural_site",
    "river": "natural_site",
    "mountain": "natural_site",
    "natural": "natural_site",
    "town": "city",
    "county": "district",
}

_SCOPE_ALIASES = {
    "poi": "place",
    "attraction": "place",
    "scenic": "place",
    "natural_site": "place",
}

_DECISION_ALIASES = {
    "best_time": "best_time_to_visit",
    "best_season": "best_time_to_visit",
    "seasonality": "best_time_to_visit",
    "opening_time": "opening_hours",
    "hours": "opening_hours",
    "price": "ticket_price",
    "crowd": "crowd_level",
    "weather": "general_advice",
}

_FAMILY_ALIASES = {
    "advice": "advisory",
    "recommendation": "advisory",
    "compare": "comparison",
    "itinerary_planning": "planning",
    "route": "planning",
}

_NEED_TYPE_ALIASES: dict[str, str] = {
    "altitude": "elevation",
    "height": "elevation",
    "海拔": "elevation",
    "高度": "elevation",
    "面积": "general_fact",
    "area": "general_fact",
    "人口": "general_fact",
    "population": "general_fact",
    "founding_year": "general_fact",
    "建成年份": "general_fact",
}


def _coerce_float(value: Any, default: float = 0.7) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("overall", "total", "score", "confidence"):
            if key in value:
                return _coerce_float(value[key], default)
        nums = [v for v in value.values() if isinstance(v, (int, float))]
        if nums:
            return float(sum(nums) / len(nums))
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _normalize_entity(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        if isinstance(raw, str) and raw.strip():
            return {"text": raw.strip(), "normalized_name": raw.strip()}
        return None

    entity = dict(raw)
    text = (
        entity.pop("text", None)
        or entity.pop("name", None)
        or entity.pop("mention", None)
        or entity.pop("place_name", None)
        or entity.pop("label", None)
        or entity.pop("value", None)
    )
    if not text:
        return None

    entity["text"] = str(text).strip()
    if not entity.get("normalized_name"):
        entity["normalized_name"] = entity["text"]

    etype = str(entity.get("entity_type") or entity.pop("type", None) or "unknown").lower()
    entity["entity_type"] = _ENTITY_TYPE_ALIASES.get(etype, etype)

    if "confidence" in entity:
        entity["confidence"] = _coerce_float(entity["confidence"])

    if entity.get("needs_verification") is None and "needs_verification" not in entity:
        entity.setdefault("needs_verification", False)

    raw_labels = entity.get("labels") or []
    if isinstance(raw_labels, str):
        raw_labels = [raw_labels]
    entity["labels"] = [str(label).strip() for label in raw_labels if str(label).strip()]

    return entity


def _normalize_information_need(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        canonical = _NEED_TYPE_ALIASES.get(raw.lower(), raw)
        return {"need_type": canonical, "priority": "medium"}
    if isinstance(raw, dict):
        need = dict(raw)
        if "need_type" not in need:
            need["need_type"] = need.pop("type", None) or need.pop("name", None) or "unknown"
        raw_type = str(need.get("need_type", "")).lower()
        if raw_type in _NEED_TYPE_ALIASES:
            need["need_type"] = _NEED_TYPE_ALIASES[raw_type]
        return need
    return {"need_type": "unknown", "priority": "medium"}


def _normalize_time_scope(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        scope = raw.lower()
        if scope in {"season", "seasonal", "monthly"}:
            return {"scope": "seasonal"}
        if scope in {"today", "now", "current"}:
            return {"scope": "current"}
        return {"scope": scope if scope in {"current", "specific_date", "month", "seasonal", "flexible", "unknown"} else "unknown"}
    if isinstance(raw, dict):
        ts = dict(raw)
        if "scope" not in ts and "type" in ts:
            ts["scope"] = ts.pop("type")
        return ts
    return {"scope": "unknown"}


def _normalize_answer_policy(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    policy = dict(raw)
    for key in list(policy.keys()):
        if key.startswith("can_use_") or key.startswith("allow_"):
            continue
        val = policy[key]
        if isinstance(val, dict) and "value" in val:
            policy[key] = val["value"]
    aliases = {
        "can_use_model_prior": "can_answer_with_model_prior",
        "model_prior_allowed": "can_answer_with_model_prior",
        "requires_live": "requires_live_data",
        "exact_fact_required": "requires_exact_fact",
    }
    for old, new in aliases.items():
        if old in policy and new not in policy:
            policy[new] = policy.pop(old)
    return policy


def _normalize_enum(value: Any, aliases: dict[str, str], default: str) -> str:
    if not value:
        return default
    key = str(value).lower().strip()
    return aliases.get(key, key)


def normalize_llm_understanding_payload(data: dict[str, Any], raw_query: str) -> dict[str, Any]:
    """Coerce common LLM field variants before Pydantic validation."""
    out = dict(data)

    out["raw_query"] = out.get("raw_query") or raw_query
    out["rewritten_query"] = out.get("rewritten_query") or out["raw_query"]
    out["confidence"] = _coerce_float(out.get("confidence"), 0.7)

    out["query_scope"] = _normalize_enum(out.get("query_scope"), _SCOPE_ALIASES, "unknown")
    out["task_family"] = _normalize_enum(out.get("task_family"), _FAMILY_ALIASES, "unknown")
    out["decision_type"] = _normalize_enum(out.get("decision_type"), _DECISION_ALIASES, "unknown")

    entities: list[dict[str, Any]] = []
    for raw_entity in out.get("entities") or []:
        normalized = _normalize_entity(raw_entity)
        if normalized:
            entities.append(normalized)
    out["entities"] = entities

    out["time_scope"] = _normalize_time_scope(out.get("time_scope") or {})

    if isinstance(out.get("user_constraints"), dict):
        uc = out["user_constraints"]
        raw_party = uc.get("party")
        if isinstance(raw_party, list):
            normalized_party: list[str] = []
            for item in raw_party:
                if isinstance(item, str):
                    normalized_party.append(item)
                elif isinstance(item, dict):
                    val = item.get("type") or item.get("name") or item.get("value") or ""
                    if isinstance(val, str) and val.strip():
                        normalized_party.append(val.strip())
                elif item is not None:
                    s = str(item).strip()
                    if s:
                        normalized_party.append(s)
            uc["party"] = normalized_party
        elif raw_party is None:
            uc["party"] = []
        else:
            uc["party"] = []
        out["user_constraints"] = uc
    else:
        out["user_constraints"] = {}

    needs: list[dict[str, Any]] = []
    for raw_need in out.get("information_needs") or []:
        needs.append(_normalize_information_need(raw_need))
    out["information_needs"] = needs

    policy_raw = out.get("answer_policy")
    if isinstance(policy_raw, dict):
        out["answer_policy"] = _normalize_answer_policy(policy_raw)
    elif policy_raw is None:
        out["answer_policy"] = {}

    if out.get("needs_clarification") is None:
        out["needs_clarification"] = False

    if isinstance(out.get("missing_critical_info"), str):
        out["missing_critical_info"] = [out["missing_critical_info"]]

    ambiguity = out.get("place_ambiguity")
    if isinstance(ambiguity, dict):
        candidates = []
        for raw in ambiguity.get("candidates") or []:
            if isinstance(raw, dict) and raw.get("name"):
                candidates.append(
                    {
                        "name": str(raw["name"]).strip(),
                        "region": raw.get("region"),
                        "city": raw.get("city"),
                        "note": raw.get("note"),
                        "confidence": _coerce_float(raw.get("confidence"), 0.5),
                    }
                )
        out["place_ambiguity"] = {
            "is_ambiguous": bool(ambiguity.get("is_ambiguous")),
            "reason": ambiguity.get("reason"),
            "candidates": candidates,
        }

    return out
