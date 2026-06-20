from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.review import ReviewAspectName, ReviewAspectResult


FACT_PATTERNS = {
    "official_hours": ["开放时间", "开放", "opening", "hours", "休馆", "闭馆"],
    "ticket_price": ["票价", "门票", "ticket", "price", "JPY", "CNY", "KRW"],
    "reservation_policy": ["预约", "reservation", "实名"],
    "weather": ["天气", "weather", "雨", "rain", "晴"],
    "transit_summary": ["交通", "地铁", "transit", "bus", "步行", "walk"],
    "food_nearby": ["餐饮", "餐厅", "food", "dining"],
    "crowd_risk": ["拥挤", "人流", "crowd", "人多"],
    "walking_intensity": ["步行", "坡", "walking", "uphill"],
}

REVIEW_ASPECT_MAP = {
    "crowd_risk": ReviewAspectName.CROWD_LEVEL,
    "walking_intensity": ReviewAspectName.WALKING_INTENSITY,
    "transit_summary": ReviewAspectName.TRANSPORT_CONVENIENCE,
    "food_nearby": ReviewAspectName.FOOD_NEARBY,
}


class CitationChecker:
    @staticmethod
    def check(
        answer: str,
        fact_sheets: list[PlaceFactSheet],
        review_results: list[ReviewAspectResult],
        base_confidence: float,
    ) -> tuple[float, list[str]]:
        limitations: list[str] = []
        penalty = 0.0
        lower = answer.lower()

        for field, keywords in FACT_PATTERNS.items():
            if not any(kw.lower() in lower or kw in answer for kw in keywords):
                continue
            backed = CitationChecker._field_backed(field, fact_sheets, review_results)
            if not backed:
                limitations.append(f"回答提及{field}，但缺少可追溯 evidence/review 支撑，已降置信度。")
                penalty += 0.08

        confidence = max(0.2, round(base_confidence - penalty, 3))
        if not fact_sheets:
            limitations.append("关键证据不足，部分结论置信度受限。")
            confidence = min(confidence, 0.45)
        return confidence, limitations

    @staticmethod
    def _field_backed(
        field: str,
        fact_sheets: list[PlaceFactSheet],
        review_results: list[ReviewAspectResult],
    ) -> bool:
        for sheet in fact_sheets:
            if sheet.has_field(field) and sheet.field_source_ids(field):
                return True
            if sheet.has_field(field) and field in {
                "walking_intensity",
                "transport_convenience",
                "crowd_risk",
                "accessibility",
                "first_timer_fit",
            }:
                return True

        aspect = REVIEW_ASPECT_MAP.get(field)
        if aspect:
            for review in review_results:
                if any(a.aspect == aspect for a in review.aspects):
                    return True
        return False
