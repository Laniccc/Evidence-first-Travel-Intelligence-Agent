"""Resolve configured official page whitelist URLs for a place name."""

from __future__ import annotations

from app.config import get_settings

_PLACE_ALIASES: dict[str, str] = {
    "故宫": "故宫博物院",
    "紫禁城": "故宫博物院",
    "forbidden city": "故宫博物院",
    "the forbidden city": "故宫博物院",
}


def resolve_official_whitelist_url(place_name: str | None) -> str | None:
    if not place_name or not str(place_name).strip():
        return None
    name = str(place_name).strip()
    settings = get_settings()
    whitelist = settings.official_page_whitelist or {}

    candidates = [name, _PLACE_ALIASES.get(name.lower(), "")]
    if "故宫" in name:
        candidates.append("故宫博物院")
        candidates.append("Forbidden City")
    lowered = name.lower()
    for key, url in whitelist.items():
        key_l = key.lower()
        if key in candidates or key_l in lowered or lowered in key_l:
            return url
        if key in name or name in key:
            return url
    try:
        from tools.mock_data import normalize_place_name

        canonical = normalize_place_name(name)
        if canonical and canonical in whitelist:
            return whitelist[canonical]
        if canonical:
            for key, url in whitelist.items():
                if key.lower() in canonical.lower() or canonical.lower() in key.lower():
                    return url
    except Exception:
        pass
    return None
