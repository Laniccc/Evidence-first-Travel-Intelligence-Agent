import re

from app.schemas.citation import CitationCheckResult
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.review import ReviewAspectName, ReviewAspectResult


class CitationChecker:
    @staticmethod
    def check(
        answer: str,
        fact_sheets: list[PlaceFactSheet],
        review_results: list[ReviewAspectResult],
        base_confidence: float,
    ) -> CitationCheckResult:
        limitations: list[str] = []
        mismatches: list[dict] = []
        penalty = 0.0

        for sheet in fact_sheets:
            penalty += CitationChecker._check_times(answer, sheet, mismatches, limitations)
            penalty += CitationChecker._check_prices(answer, sheet, mismatches, limitations)
            penalty += CitationChecker._check_reservation(answer, sheet, mismatches, limitations)
            penalty += CitationChecker._check_weather(answer, sheet, mismatches, limitations)
            penalty += CitationChecker._check_transit(answer, sheet, mismatches, limitations)

        penalty += CitationChecker._check_experience_claims(answer, fact_sheets, review_results, mismatches, limitations)

        confidence = max(0.2, round(base_confidence - penalty, 3))
        if not fact_sheets:
            limitations.append("关键证据不足，部分结论置信度受限。")
            confidence = min(confidence, 0.45)
        if mismatches:
            limitations.append("答案中某些具体表述未能与证据值完全匹配，已降置信度。")

        return CitationCheckResult(
            confidence=confidence,
            limitations=limitations,
            unsupported_or_mismatched_claims=mismatches,
        )

    @staticmethod
    def _check_times(answer: str, sheet: PlaceFactSheet, mismatches: list, limitations: list) -> float:
        if not sheet.official_hours:
            return 0.0
        times_in_answer = CitationChecker.extract_time_claims(answer)
        if not times_in_answer:
            return 0.0
        norm_sheet = CitationChecker.normalize_time_text(sheet.official_hours)
        if any(CitationChecker.fuzzy_contains_or_equivalent(t, norm_sheet) for t in times_in_answer):
            return 0.0
        mismatches.append({"field": "opening_hours", "answer_fragments": times_in_answer, "expected": sheet.official_hours})
        limitations.append("回答中的开放时间与证据不完全一致。")
        return 0.1

    @staticmethod
    def _check_prices(answer: str, sheet: PlaceFactSheet, mismatches: list, limitations: list) -> float:
        if not sheet.ticket_price:
            return 0.0
        prices = CitationChecker.extract_price_claims(answer)
        if not prices:
            return 0.0
        norm_sheet = CitationChecker.normalize_price_text(sheet.ticket_price)
        if any(CitationChecker.fuzzy_contains_or_equivalent(p, norm_sheet) for p in prices):
            return 0.0
        mismatches.append({"field": "ticket_price", "answer_fragments": prices, "expected": sheet.ticket_price})
        limitations.append("回答中的票价与证据不完全一致。")
        return 0.1

    @staticmethod
    def _check_reservation(answer: str, sheet: PlaceFactSheet, mismatches: list, limitations: list) -> float:
        claims = CitationChecker.extract_reservation_claims(answer)
        if not claims or not sheet.reservation_policy:
            return 0.0
        policy = sheet.reservation_policy.lower()
        required = "required" in policy or "预约" in policy or "实名" in policy
        penalty = 0.0
        for c in claims:
            if c == "required" and not required:
                mismatches.append({"field": "reservation_policy", "claim": c, "expected": sheet.reservation_policy})
                penalty += 0.08
            if c == "not_required" and required:
                mismatches.append({"field": "reservation_policy", "claim": c, "expected": sheet.reservation_policy})
                penalty += 0.08
        return penalty

    @staticmethod
    def _check_weather(answer: str, sheet: PlaceFactSheet, mismatches: list, limitations: list) -> float:
        weather_claims = CitationChecker.extract_weather_claims(answer)
        if not weather_claims:
            return 0.0
        if sheet.weather:
            return 0.0
        mismatches.append({"field": "weather", "answer_fragments": weather_claims})
        limitations.append("回答提及天气但缺少 weather 证据支撑。")
        return 0.08

    @staticmethod
    def _check_transit(answer: str, sheet: PlaceFactSheet, mismatches: list, limitations: list) -> float:
        if not any(k in answer for k in ["地铁", "公交", "transit", "bus", "metro", "步行", "walk"]):
            return 0.0
        if sheet.transit_summary:
            return 0.0
        mismatches.append({"field": "transit_summary", "reason": "missing evidence"})
        limitations.append("回答提及交通但缺少 transit 证据支撑。")
        return 0.06

    @staticmethod
    def _check_experience_claims(
        answer: str,
        fact_sheets: list[PlaceFactSheet],
        review_results: list[ReviewAspectResult],
        mismatches: list,
        limitations: list,
    ) -> float:
        exp_keywords = ["拥挤", "排队", "步行", "老人", "crowd", "queue", "walking", "elderly"]
        if not any(k in answer.lower() or k in answer for k in exp_keywords):
            return 0.0
        backed = any(sheet.crowd_risk is not None or sheet.walking_intensity is not None for sheet in fact_sheets)
        backed = backed or any(review.aspects for review in review_results)
        if backed:
            return 0.0
        mismatches.append({"field": "experience", "reason": "no fact_sheet or review aspect"})
        limitations.append("体验判断缺少 fact_sheet 或 review_aspects 支撑。")
        return 0.08

    @staticmethod
    def extract_time_claims(answer: str) -> list[str]:
        return re.findall(r"\d{1,2}:\d{2}", answer)

    @staticmethod
    def extract_price_claims(answer: str) -> list[str]:
        return re.findall(r"\d+\s*(?:JPY|CNY|KRW|元|円|원)", answer, flags=re.I)

    @staticmethod
    def extract_reservation_claims(answer: str) -> list[str]:
        claims = []
        if any(x in answer for x in ["需要预约", "必须预约", "reservation required", "实名预约"]):
            claims.append("required")
        if any(x in answer for x in ["无需预约", "not required", "不需要预约"]):
            claims.append("not_required")
        if any(x in answer for x in ["建议预约", "recommended to book"]):
            claims.append("recommended")
        return claims

    @staticmethod
    def extract_weather_claims(answer: str) -> list[str]:
        keywords = ["雨", "rain", "晴", "sunny", "高温", "寒冷", "cloud", "多云", "weather", "天气"]
        return [k for k in keywords if k.lower() in answer.lower() or k in answer]

    @staticmethod
    def normalize_time_text(text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    @staticmethod
    def normalize_price_text(text: str) -> str:
        return re.sub(r"\s+", "", text.upper())

    @staticmethod
    def fuzzy_contains_or_equivalent(fragment: str, canonical: str) -> bool:
        frag = fragment.lower().replace(" ", "")
        canon = canonical.lower().replace(" ", "")
        return frag in canon or canon in frag
