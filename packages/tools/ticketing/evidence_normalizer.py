"""Normalize ticket/review provider payloads into Evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.evidence import Claim, ClaimType, Evidence, LicenseScope, SourceType

TICKETLENS_LIMITATION = (
    "TicketLens 提供票务/体验候选信息，具体价格与库存以平台实时页面为准。"
)
CTrip_LIMITATION = "评论爬虫结果为游客反馈信号，不代表官方票价或公告。"
FLIGGY_LIMITATION = "飞猪 API 返回平台候选票务信息，价格与库存以平台实时页面为准。"
DIANPING_LIMITATION = "大众点评爬虫结果为游客反馈信号，不代表官方票价或公告。"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(conf: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, conf))


def _truncate_snippets(values: list[Any], *, max_items: int = 3, max_len: int = 200) -> list[str]:
    out: list[str] = []
    for raw in values[:max_items]:
        text = str(raw).strip()
        if text:
            out.append(text[:max_len])
    return out


def normalize_ticketlens_items(
    items: list[dict[str, Any]],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
    mode: str = "ticket",
) -> list[Evidence]:
    evidence_list: list[Evidence] = []
    for item in items[:10]:
        claims: list[Claim] = []
        price = item.get("price")
        price_text = item.get("price_text") or item.get("priceText")
        if price is not None or price_text:
            claims.append(
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value=price_text or str(price),
                    confidence=_clamp(float(item.get("confidence", 0.65)), 0.55, 0.75),
                )
            )
            if item.get("activity_name") or item.get("ticket_type"):
                claims.append(
                    Claim(
                        claim_type=ClaimType.ACTIVITY_PRICE,
                        value=item.get("activity_name") or item.get("ticket_type"),
                        confidence=0.6,
                    )
                )
        if item.get("booking_channel") or item.get("channel"):
            claims.append(
                Claim(
                    claim_type=ClaimType.BOOKING_CHANNEL,
                    value=str(item.get("booking_channel") or item.get("channel")),
                    confidence=0.65,
                )
            )
        if item.get("ticket_type"):
            claims.append(
                Claim(
                    claim_type=ClaimType.TICKET_TYPE,
                    value=str(item["ticket_type"]),
                    confidence=0.6,
                )
            )
        if item.get("url") or item.get("source_url"):
            claims.append(
                Claim(
                    claim_type=ClaimType.PLATFORM_TICKET_URL,
                    value=str(item.get("url") or item.get("source_url")),
                    confidence=0.6,
                )
            )
        if mode == "review":
            rating = item.get("rating")
            review_count = item.get("review_count")
            if rating is not None:
                claims.append(
                    Claim(claim_type=ClaimType.RATING_CANDIDATE, value=rating, confidence=0.55)
                )
            if review_count is not None:
                claims.append(
                    Claim(claim_type=ClaimType.REVIEW_COUNT, value=review_count, confidence=0.55)
                )
            summary = item.get("review_summary") or item.get("summary")
            if summary:
                claims.append(
                    Claim(
                        claim_type=ClaimType.REVIEW_SUMMARY,
                        value=str(summary)[:500],
                        confidence=0.55,
                    )
                )
        if not claims:
            continue
        conf = _clamp(float(item.get("confidence", 0.65)), 0.55, 0.75)
        evidence_list.append(
            Evidence(
                source_name="TicketLens",
                source_type=SourceType.TICKET_PLATFORM,
                source_url=item.get("url") or item.get("source_url"),
                country=country,
                city=city,
                place_name=place_name,
                confidence=conf,
                license_scope=LicenseScope.API_ALLOWED,
                claims=claims,
                limitations=[TICKETLENS_LIMITATION],
            )
        )
    return evidence_list


def normalize_review_crawler_payload(
    provider: str,
    payload: dict[str, Any],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
) -> list[Evidence]:
    limitation = CTrip_LIMITATION if provider.lower().startswith("ctrip") else DIANPING_LIMITATION
    if "fliggy" in provider.lower():
        limitation = "飞猪评论信号为游客反馈摘要，不代表官方票价。"
    items = payload.get("items") or payload.get("reviews") or [payload]
    if not isinstance(items, list):
        items = [items]
    evidence_list: list[Evidence] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        claims: list[Claim] = []
        summary = item.get("review_summary") or item.get("summary")
        if summary:
            claims.append(
                Claim(
                    claim_type=ClaimType.REVIEW_SUMMARY,
                    value=str(summary)[:500],
                    confidence=_clamp(float(item.get("confidence", 0.55)), 0.45, 0.65),
                )
            )
        for aspect in _truncate_snippets(item.get("positive_aspects") or []):
            claims.append(
                Claim(claim_type=ClaimType.REVIEW_ASPECT, value=f"+ {aspect}", confidence=0.5)
            )
        for aspect in _truncate_snippets(item.get("negative_aspects") or []):
            claims.append(
                Claim(claim_type=ClaimType.REVIEW_ASPECT, value=f"- {aspect}", confidence=0.5)
            )
        for mention in _truncate_snippets(item.get("ticket_related_mentions") or []):
            claims.append(
                Claim(
                    claim_type=ClaimType.TICKET_RELATED_MENTIONS,
                    value=mention,
                    confidence=0.5,
                )
            )
        if item.get("value_for_money"):
            claims.append(
                Claim(
                    claim_type=ClaimType.REVIEW_ASPECT,
                    value=f"value_for_money: {item['value_for_money']}",
                    confidence=0.5,
                )
            )
        if item.get("crowd_risk"):
            claims.append(
                Claim(claim_type=ClaimType.CROWD, value=str(item["crowd_risk"]), confidence=0.5)
            )
        if item.get("queue_risk"):
            claims.append(
                Claim(claim_type=ClaimType.CROWD, value=f"queue: {item['queue_risk']}", confidence=0.5)
            )
        heat = item.get("heat_score")
        if heat is not None:
            try:
                heat_val = float(heat)
                level = "high" if heat_val >= 7 else "medium" if heat_val >= 4 else "low"
                claims.append(
                    Claim(
                        claim_type=ClaimType.CROWD,
                        value=f"heat_score: {heat_val} ({level})",
                        confidence=0.48,
                    )
                )
            except (TypeError, ValueError):
                pass
        price_text = item.get("price_text") or item.get("ticket_price_mention")
        if price_text:
            claims.append(
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value=str(price_text),
                    confidence=0.45,
                )
            )
        if not claims:
            continue
        evidence_list.append(
            Evidence(
                source_name=f"{provider} Crawler",
                source_type=SourceType.REVIEW_PLATFORM,
                source_url=item.get("source_url") or item.get("url"),
                country=country,
                city=city,
                place_name=place_name,
                confidence=_clamp(float(item.get("confidence", 0.55)), 0.45, 0.65),
                claims=claims,
                limitations=[limitation],
            )
        )
    return evidence_list


def normalize_fliggy_ticket_payload(
    payload: dict[str, Any],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
    review_mode: bool = False,
) -> list[Evidence]:
    if review_mode:
        return normalize_review_crawler_payload(
            "Fliggy", payload, place_name=place_name, city=city, country=country
        )
    items = payload.get("items") or payload.get("tickets") or [payload]
    if not isinstance(items, list):
        items = [items]
    evidence_list: list[Evidence] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        claims: list[Claim] = []
        price = item.get("price")
        price_text = item.get("price_text")
        if price is not None or price_text:
            claims.append(
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value=price_text or str(price),
                    confidence=_clamp(float(item.get("confidence", 0.55)), 0.45, 0.70),
                )
            )
        ticket_title = str(item.get("ticket_title") or "").strip()
        ticket_name = str(item.get("ticket_name") or "").strip()
        ticket_type = str(item.get("ticket_type") or "").strip()
        if ticket_title:
            claims.append(
                Claim(
                    claim_type=ClaimType.ACTIVITY_PRICE,
                    value=ticket_title,
                    normalized_value={
                        "ticket_title": ticket_title,
                        "ticket_name": ticket_name or ticket_type,
                    },
                    confidence=0.58,
                )
            )
        if ticket_type or ticket_name:
            display_type = ticket_type or ticket_name
            if ticket_title and ticket_name and ticket_name not in ticket_title:
                display_type = f"{ticket_title} - {ticket_name}"
            claims.append(
                Claim(claim_type=ClaimType.TICKET_TYPE, value=display_type, confidence=0.55)
            )
        if item.get("sales_status"):
            claims.append(
                Claim(
                    claim_type=ClaimType.SALES_STATUS,
                    value=str(item["sales_status"]),
                    confidence=0.55,
                )
            )
        if item.get("booking_channel"):
            claims.append(
                Claim(
                    claim_type=ClaimType.BOOKING_CHANNEL,
                    value=str(item["booking_channel"]),
                    confidence=0.55,
                )
            )
        url = item.get("platform_ticket_url") or item.get("url")
        if url:
            claims.append(
                Claim(claim_type=ClaimType.PLATFORM_TICKET_URL, value=str(url), confidence=0.55)
            )
        captured = item.get("captured_at") or _utc_now_iso()
        claims.append(Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=f"captured_at:{captured}", confidence=0.4))
        if not claims:
            continue
        source = str(item.get("source") or "").lower()
        source_name = "Fliggy Open API"
        if "flyai" in source:
            source_name = "Fliggy FlyAI"
        elif "subprocess" in source or "crawler" in source:
            source_name = "Fliggy Crawler"
        evidence_list.append(
            Evidence(
                source_name=source_name,
                source_type=SourceType.TICKET_PLATFORM,
                source_url=url,
                country=country,
                city=city,
                place_name=place_name,
                confidence=_clamp(float(item.get("confidence", 0.55)), 0.45, 0.70),
                claims=claims,
                limitations=[FLIGGY_LIMITATION],
            )
        )
    return evidence_list


def normalize_dianping_payload(
    payload: dict[str, Any],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
    ticket_signal: bool = False,
) -> list[Evidence]:
    if ticket_signal:
        items = payload.get("items") or [payload]
        evidence_list: list[Evidence] = []
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            claims: list[Claim] = []
            for mention in item.get("ticket_related_mentions") or []:
                claims.append(
                    Claim(
                        claim_type=ClaimType.TICKET_RELATED_MENTIONS,
                        value=str(mention)[:200],
                        confidence=0.45,
                    )
                )
            price_text = item.get("price_text")
            if price_text:
                claims.append(
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value=str(price_text),
                        confidence=0.45,
                    )
                )
            if not claims:
                continue
            evidence_list.append(
                Evidence(
                    source_name="Dianping Crawler",
                    source_type=SourceType.REVIEW_PLATFORM,
                    source_url=item.get("source_url"),
                    country=country,
                    city=city,
                    place_name=place_name,
                    confidence=0.5,
                    claims=claims,
                    limitations=[DIANPING_LIMITATION],
                )
            )
        return evidence_list
    return normalize_review_crawler_payload(
        "Dianping", payload, place_name=place_name, city=city, country=country
    )


def normalize_guide_crawler_payload(
    provider: str,
    payload: dict[str, Any],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
) -> list[Evidence]:
    items = payload.get("items") or [payload]
    if not isinstance(items, list):
        items = [items]
    evidence_list: list[Evidence] = []
    limitation = f"{provider} 攻略/季节信号来自平台页面摘要，非官方运营公告。"
    for item in items[:15]:
        if not isinstance(item, dict):
            continue
        claims: list[Claim] = []
        season = item.get("seasonality") or item.get("best_time_to_visit")
        summary = item.get("review_summary") or item.get("summary")
        if season:
            claims.append(
                Claim(claim_type=ClaimType.SEASONALITY, value=str(season)[:500], confidence=0.5)
            )
            claims.append(
                Claim(
                    claim_type=ClaimType.BEST_TIME_TO_VISIT,
                    value=str(season)[:500],
                    confidence=0.5,
                )
            )
        elif summary:
            claims.append(
                Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=str(summary)[:500], confidence=0.45)
            )
        if not claims:
            continue
        evidence_list.append(
            Evidence(
                source_name=f"{provider} Guide",
                source_type=SourceType.REVIEW_PLATFORM,
                source_url=item.get("source_url") or item.get("url"),
                country=country,
                city=city,
                place_name=place_name,
                confidence=_clamp(float(item.get("confidence", 0.5)), 0.4, 0.6),
                claims=claims,
                limitations=[limitation],
            )
        )
    return evidence_list


def normalize_nearby_crawler_payload(
    provider: str,
    payload: dict[str, Any],
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
) -> list[Evidence]:
    items = payload.get("items") or payload.get("nearby_poi") or [payload]
    if not isinstance(items, list):
        items = [items]
    evidence_list: list[Evidence] = []
    limitation = f"{provider} 附近 POI 为平台搜索候选，距离与营业状态需二次核实。"
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        name = item.get("shop_name") or item.get("name") or item.get("title")
        if not name:
            continue
        claims: list[Claim] = [
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=str(name)[:200],
                confidence=0.5,
            ),
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value=f"nearby_poi: {name}",
                confidence=0.45,
            ),
        ]
        if item.get("address"):
            claims.append(
                Claim(claim_type=ClaimType.ADDRESS, value=str(item["address"])[:200], confidence=0.45)
            )
        rating = item.get("rating")
        review_count = item.get("review_count") or item.get("comment_count")
        if rating is not None:
            claims.append(
                Claim(
                    claim_type=ClaimType.RATING_CANDIDATE,
                    value=f"评分 {rating}" + (f"（{review_count}条评价）" if review_count else ""),
                    normalized_value={
                        "rating": rating,
                        "review_count": review_count,
                        "shop_name": name,
                    },
                    confidence=0.62,
                )
            )
        price_level = item.get("price_level") or item.get("avg_price")
        if price_level:
            claims.append(
                Claim(claim_type=ClaimType.PRICE_CANDIDATE, value=str(price_level), confidence=0.4)
            )
        category = item.get("main_category") or item.get("category")
        food_bits = [str(name)[:120]]
        if rating is not None:
            food_bits.append(f"评分{rating}")
        if review_count:
            food_bits.append(f"{review_count}条评价")
        if category and "餐" in str(category):
            claims.append(
                Claim(
                    claim_type=ClaimType.FOOD,
                    value="，".join(food_bits),
                    normalized_value={
                        "name": name,
                        "rating": rating,
                        "review_count": review_count,
                        "information_need": "nearby_food",
                    },
                    confidence=0.58,
                )
            )
        evidence_list.append(
            Evidence(
                source_name=f"{provider} Nearby",
                source_type=SourceType.FOOD_PLATFORM,
                source_url=item.get("source_url") or item.get("url"),
                country=country,
                city=city,
                place_name=place_name,
                confidence=_clamp(float(item.get("confidence", 0.5)), 0.4, 0.55),
                claims=claims,
                limitations=[limitation],
            )
        )
    return evidence_list


def normalize_crowd_estimation_payload(
    *,
    place_name: str,
    city: str | None = None,
    country: str = "China",
    score: float,
    label: str,
    sources: list[str],
    detail: str | None = None,
) -> list[Evidence]:
    claims = [
        Claim(
            claim_type=ClaimType.CROWD,
            value={"score": round(score, 2), "level": label},
            confidence=_clamp(0.35 + score * 0.35, 0.35, 0.65),
        ),
        Claim(
            claim_type=ClaimType.TRAVEL_ADVICE,
            value=f"current_crowd_estimate: {label} ({score:.2f})",
            confidence=0.45,
        ),
    ]
    if detail:
        claims.append(
            Claim(claim_type=ClaimType.CONGESTION_RISK, value=detail[:300], confidence=0.4)
        )
    return [
        Evidence(
            source_name="Crowd Estimation",
            source_type=SourceType.REVIEW_PLATFORM,
            country=country,
            city=city,
            place_name=place_name,
            confidence=0.5,
            claims=claims,
            limitations=[
                "拥挤度为平台评论/热度/路况信号融合估计，非实时官方客流数据。",
                "sources: " + ", ".join(sources),
            ],
        )
    ]
