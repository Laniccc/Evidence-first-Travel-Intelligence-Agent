"""Map intent subtypes / raw needs to canonical LOOKUP claim types."""

from __future__ import annotations

import re

_LOOKUP_NEED_ALIASES: dict[str, str] = {
    "height_elevation": "elevation",
    "altitude": "elevation",
    "mountain_height": "elevation",
    "peak_height": "elevation",
    "geo_numeric": "elevation",
}

_ELEVATION_TEXT = re.compile(r"海拔|高度|altitude|elevation|主峰|最高峰|山体高度", re.I)


def resolve_lookup_need(need: str) -> str:
    raw = (need or "").strip()
    if not raw:
        return raw
    return _LOOKUP_NEED_ALIASES.get(raw, raw)


def is_elevation_lookup_text(text: str) -> bool:
    return bool(_ELEVATION_TEXT.search(text or ""))


def infer_lookup_needs_from_text(text: str) -> list[str]:
    needs: list[str] = []
    if is_elevation_lookup_text(text):
        needs.append("elevation")
    return needs


def infer_lookup_needs_from_intent_subtypes(subtypes: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in subtypes or []:
        mapped = resolve_lookup_need(str(raw))
        if mapped and mapped not in out:
            out.append(mapped)
    return out
