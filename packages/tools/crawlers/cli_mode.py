"""Map S5 claim_type / crawler_mode to CLI --mode values."""

from __future__ import annotations

_CLAIM_TO_CLI_MODE: dict[str, str] = {
    "review": "review",
    "review_summary": "review",
    "reputation": "review",
    "value_rating": "review",
    "ticket": "ticket",
    "ticket_price": "ticket",
    "ticket_price_candidate": "ticket",
    "nearby": "nearby",
    "nearby_food": "nearby",
    "nearby_poi": "nearby",
    "nearby_hotel": "nearby",
    "guide": "guide",
    "seasonality": "guide",
    "best_time_to_visit": "guide",
    "crowd": "crowd",
    "crowd_level": "crowd",
    "current_crowd_estimate": "crowd",
    "queue_risk": "crowd",
}

_VALID_MODES = frozenset({"review", "ticket", "nearby", "guide", "crowd"})


def resolve_crawler_cli_mode(*, crawler_mode: str | None, claim_type: str | None) -> str:
    if crawler_mode and crawler_mode.strip().lower() in _VALID_MODES:
        return crawler_mode.strip().lower()
    for candidate in (claim_type, crawler_mode):
        if not candidate:
            continue
        key = str(candidate).strip().lower()
        if key in _VALID_MODES:
            return key
        mapped = _CLAIM_TO_CLI_MODE.get(key)
        if mapped:
            return mapped
    return "review"
