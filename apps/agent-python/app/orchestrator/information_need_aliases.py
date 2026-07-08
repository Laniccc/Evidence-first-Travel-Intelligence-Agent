"""Normalize information_need aliases before S3 contract / S5 domain planning."""

from __future__ import annotations

from app.orchestrator.lookup_need_aliases import resolve_lookup_need
from app.orchestrator.nearby_category_registry import (
    CANONICAL_NEARBY_NEEDS,
    GENERIC_NEARBY_NEEDS,
    NEED_ALIASES,
    infer_all_nearby_needs_from_text,
    infer_nearby_need_from_text,
    normalize_canonical_need,
)

NEARBY_PATTERN = __import__("re").compile(r"附近|周边|顺路", __import__("re").I)

# Re-export for backward compatibility
_NEARBY_NEEDS = CANONICAL_NEARBY_NEEDS
_GENERIC_NEARBY_NEEDS = GENERIC_NEARBY_NEEDS


def normalize_need(need: str) -> str:
    return NEED_ALIASES.get(need, need)


def resolve_nearby_need(need: str, *, text: str = "") -> str:
    """Canonical nearby need for contract, retrieval, and composition."""
    n = normalize_need(need)
    if n in _NEARBY_NEEDS:
        return n
    if n in _GENERIC_NEARBY_NEEDS:
        return infer_nearby_need_from_text(text)
    return n


def is_nearby_need(need: str) -> bool:
    n = normalize_need(need)
    return n in _NEARBY_NEEDS or n in _GENERIC_NEARBY_NEEDS


def nearby_needs_set(needs: set[str] | list[str]) -> set[str]:
    return {resolve_nearby_need(n) for n in needs if is_nearby_need(n)} & _NEARBY_NEEDS


def normalize_information_needs(needs: list[str] | None, *, text: str = "") -> list[str]:
    if not needs:
        inferred = infer_all_nearby_needs_from_text(text)
        if len(inferred) > 1 or (inferred and inferred != ["nearby_poi"]):
            return inferred
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in needs:
        if is_nearby_need(raw):
            canonical = resolve_nearby_need(raw, text=text)
        else:
            canonical = resolve_lookup_need(normalize_need(raw))
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    if len(result) == 1 and is_nearby_need(needs[0]):
        all_inferred = infer_all_nearby_needs_from_text(text)
        if len(all_inferred) > 1:
            return all_inferred
    return result


def all_nearby_needs_from_text(text: str) -> list[str]:
    return infer_all_nearby_needs_from_text(text)


def primary_nearby_need_from_text(text: str) -> str:
    return infer_nearby_need_from_text(text)


def query_text_from_state(state) -> str:
    frame = getattr(state, "semantic_frame", None)
    parts: list[str] = []
    if frame:
        parts.extend([frame.raw_query or "", frame.normalized_request or ""])
    parts.append(getattr(state, "raw_user_query", "") or "")
    contract = getattr(state, "response_contract", None)
    if contract and contract.user_goal_summary:
        parts.append(contract.user_goal_summary)
    return " ".join(p for p in parts if p).strip()


def all_nearby_needs_from_state(state) -> list[str]:
    """All distinct nearby needs from contract, frame, or query text."""
    text = query_text_from_state(state)
    needs: list[str] = []
    seen: set[str] = set()

    contract = getattr(state, "response_contract", None)
    if contract:
        for req in contract.claim_requirements:
            if is_nearby_need(req.claim_type):
                canonical = resolve_nearby_need(req.claim_type, text=text)
                if canonical not in seen:
                    seen.add(canonical)
                    needs.append(canonical)

    frame = getattr(state, "semantic_frame", None)
    if frame and frame.information_needs:
        for need in frame.information_needs:
            if is_nearby_need(need):
                canonical = resolve_nearby_need(need, text=text)
                if canonical not in seen:
                    seen.add(canonical)
                    needs.append(canonical)

    if needs:
        return needs

    if NEARBY_PATTERN.search(text):
        return infer_all_nearby_needs_from_text(text)
    return ["nearby_poi"]


def nearby_claims_for_retrieval(state) -> list[str]:
    """Nearby needs that should trigger post-anchor retrieval (contract/frame aware)."""
    text = query_text_from_state(state)
    needs: list[str] = []
    seen: set[str] = set()

    contract = getattr(state, "response_contract", None)
    if contract:
        for req in contract.claim_requirements:
            if is_nearby_need(req.claim_type):
                canonical = resolve_nearby_need(req.claim_type, text=text)
                if canonical not in seen:
                    seen.add(canonical)
                    needs.append(canonical)

    frame = getattr(state, "semantic_frame", None)
    if frame and frame.information_needs:
        for need in frame.information_needs:
            if is_nearby_need(need):
                canonical = resolve_nearby_need(need, text=text)
                if canonical not in seen:
                    seen.add(canonical)
                    needs.append(canonical)

    if needs:
        if len(needs) == 1:
            all_inferred = infer_all_nearby_needs_from_text(text)
            if len(all_inferred) > 1:
                return all_inferred
        return needs
    return []


def primary_nearby_need_from_state(state) -> str:
    """First required nearby need from contract/frame, else infer from query text."""
    all_needs = all_nearby_needs_from_state(state)
    return all_needs[0] if all_needs else "nearby_poi"
