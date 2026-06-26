"""Search query templates for official source discovery (S5 context)."""

from __future__ import annotations

OFFICIAL_SEARCH_QUERY_TEMPLATES: dict[str, list[str]] = {
    "ticket_price": [
        "{place_name} 官网 门票",
        "{place_name} 景区 官方 票价",
        "{city} {place_name} 门票 官方",
        "{place_name} 管委会 门票",
    ],
    "opening_hours": [
        "{place_name} 官网 开放时间",
        "{place_name} 营业时间 官方",
        "{city} {place_name} 开放时间",
    ],
    "temporary_closure": [
        "{place_name} 官方 闭园 通知",
        "{place_name} 暂停开放 公告",
    ],
    "reservation_policy": [
        "{place_name} 官网 预约",
        "{place_name} 门票 预约 官方",
    ],
    "seasonal_operation_status": [
        "{place_name} 官方 开放 时间",
        "{place_name} 季节性 开放 公告",
        "{city} {place_name} 闭园 通知",
    ],
    "road_opening_period": [
        "{place_name} 道路 开放 官方 公告",
        "{city} {place_name} 通行 时间",
    ],
    "elevation": [
        "{place_name} 海拔",
        "{region} {place_name} 海拔",
        "{city} {place_name} 海拔",
    ],
    "general_fact": [
        "{region} {place_name} {user_query}",
        "{place_name} {user_query}",
    ],
}


def templates_for_claim(
    claim_type: str | None,
    *,
    place_name: str = "",
    city: str = "",
    region: str = "",
    user_query: str = "",
) -> list[str]:
    raw = OFFICIAL_SEARCH_QUERY_TEMPLATES.get(claim_type or "", [])
    return [
        t.format(
            place_name=place_name or "目的地",
            city=city or "",
            region=region or "",
            user_query=user_query or "",
        )
        for t in raw
    ]
