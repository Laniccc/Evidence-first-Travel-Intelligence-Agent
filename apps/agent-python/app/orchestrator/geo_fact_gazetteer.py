"""Small curated fallback for stable China mountain elevation facts.

This is not model prior. It emits Evidence rows from a maintained local
gazetteer only when live/web geo sources failed to produce an elevation clue.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestrator.fact_lookup_policy import collect_fact_clues, primary_fact_need_from_state
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.user_query import TravelAgentState


@dataclass(frozen=True)
class GeoFactRow:
    aliases: tuple[str, ...]
    place_name: str
    value: str
    source_name: str
    source_url: str
    confidence: float = 0.72


_ROWS: tuple[GeoFactRow, ...] = (
    GeoFactRow(
        aliases=("\u9ec4\u5c71", "\u9ec4\u5c71\u98ce\u666f\u533a"),
        place_name="\u9ec4\u5c71",
        value=(
            "\u9ec4\u5c71\u6700\u9ad8\u5cf0\u4e3a\u83b2\u82b1\u5cf0\uff0c"
            "\u6d77\u62d4\u7ea61864.8\u7c73\uff1b\u4e09\u5927\u4e3b\u5cf0\u4e2d"
            "\u5149\u660e\u9876\u7ea61860\u7c73\uff0c\u5929\u90fd\u5cf0\u7ea61810\u7c73\u3002"
        ),
        source_name="Curated China mountain gazetteer (Wikipedia/Wikidata cross-check)",
        source_url="https://zh.wikipedia.org/wiki/%E9%BB%84%E5%B1%B1",
    ),
    GeoFactRow(
        aliases=("\u6cf0\u5c71", "\u6cf0\u5c71\u98ce\u666f\u533a"),
        place_name="\u6cf0\u5c71",
        value=(
            "\u6cf0\u5c71\u4e3b\u5cf0\u4e3a\u7389\u7687\u9876\uff0c"
            "\u5e38\u89c1\u6d77\u62d4\u53e3\u5f84\u4e3a1532.7\u7c73\uff1b"
            "\u90e8\u5206\u4e2d\u6587\u65c5\u6e38\u8d44\u6599\u4e5f\u4f7f\u75281545\u7c73\u53e3\u5f84\u3002"
        ),
        source_name="Curated China mountain gazetteer (Wikipedia/Wikidata cross-check)",
        source_url="https://zh.wikipedia.org/wiki/%E6%B3%B0%E5%B1%B1",
        confidence=0.68,
    ),
)


def supplement_elevation_from_gazetteer(state: TravelAgentState) -> list[Evidence]:
    """Append stable local gazetteer evidence for elevation when retrieval is empty."""
    if primary_fact_need_from_state(state) != "elevation":
        return []
    if collect_fact_clues(state):
        return []
    query = _query_text(state)
    row = next((r for r in _ROWS if any(alias in query for alias in r.aliases)), None)
    if row is None:
        return []
    evidence = Evidence(
        source_name=row.source_name,
        source_type=SourceType.WEB,
        source_url=row.source_url,
        country="China",
        place_name=row.place_name,
        data_freshness=DataFreshness.STALE,
        license_scope=LicenseScope.PUBLIC_PAGE,
        confidence=row.confidence,
        claims=[
            Claim(
                claim_type=ClaimType.ELEVATION,
                value=row.value,
                raw_text=row.value,
                confidence=row.confidence,
            )
        ],
        limitations=[
            "Local gazetteer fallback used because configured live encyclopedia/geographic tools returned no usable elevation evidence.",
            "Treat as stable reference evidence, not a live official page read.",
        ],
    )
    state.evidence.append(evidence)
    structured = dict(state.structured_result or {})
    structured.setdefault("geo_fact_gazetteer_used", []).append(
        {"place_name": row.place_name, "claim_type": "elevation", "source_url": row.source_url}
    )
    state.structured_result = structured
    return [evidence]


def _query_text(state: TravelAgentState) -> str:
    parts = [state.raw_user_query or ""]
    frame = state.semantic_frame
    if frame:
        parts.append(frame.normalized_request or "")
        if frame.entities:
            parts.extend(frame.entities.places or [])
    return " ".join(parts)
