from app.schemas.review import ReviewAspect, ReviewAspectName, ReviewInputItem

MULTILANG_ASPECT_KEYWORDS: dict[ReviewAspectName, list[str]] = {
    ReviewAspectName.CROWD_LEVEL: [
        "crowd", " crowded", "人多", "密集", "旅行团", "混雑", "観光客", "多すぎる", "혼잡", "사람 많음", "관광객",
    ],
    ReviewAspectName.QUEUE_TIME: ["queue", "line", "排队", "行列", "대기"],
    ReviewAspectName.PHOTO_EXPERIENCE: ["photo", "拍照", "出片", "映える", "포토존", "photo spot", "view"],
    ReviewAspectName.ELDERLY_FRIENDLINESS: ["elderly", "senior", "老人", "父母", "高齢者", "어르신", "坡"],
    ReviewAspectName.WALKING_INTENSITY: [
        "walk", "hike", "uphill", "steep", "坡", "走", "坂道", "階段", "疲れる", "경사", "계단", "힘들다", "腿累",
    ],
    ReviewAspectName.ACCESSIBILITY: ["wheelchair", "mobility", "无障碍", "不方便", "stroller"],
    ReviewAspectName.TRANSPORT_CONVENIENCE: ["metro", "bus", "station", "地铁", "交通", "公共交通"],
    ReviewAspectName.FAMILY_FRIENDLINESS: ["family", "kids", "children", "亲子", "带娃", "子連れ", "아이와"],
    ReviewAspectName.VALUE_FOR_MONEY: ["value", "性价比", "overpriced", "商业化", "観光客", "비싸"],
    ReviewAspectName.FIRST_TIMER_FIT: ["must-see", "iconic", "first", "经典", "第一次"],
    ReviewAspectName.OVERRATED_RISK: ["overrated", "名不副实", "失望"],
    ReviewAspectName.COMMERCIALIZATION: ["commercial", "商业化", "商店太多"],
    ReviewAspectName.FOOD_NEARBY: ["food", "restaurant", "餐饮", "餐厅"],
}


NEGATIVE_ASPECTS = {
    ReviewAspectName.CROWD_LEVEL,
    ReviewAspectName.QUEUE_TIME,
    ReviewAspectName.WALKING_INTENSITY,
    ReviewAspectName.OVERRATED_RISK,
}


class RuleReviewAspectExtractor:
    def extract(self, reviews: list[ReviewInputItem]) -> list[ReviewAspect]:
        aspects: list[ReviewAspect] = []
        combined = " ".join(r.text.lower() for r in reviews)
        for aspect, keywords in MULTILANG_ASPECT_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw.lower() in combined or kw in combined)
            if hits == 0:
                continue
            sentiment = "negative" if aspect in NEGATIVE_ASPECTS else "positive"
            severity = "high" if hits >= 2 and aspect in NEGATIVE_ASPECTS else "medium" if hits else "low"
            examples = [r.text[:120] for r in reviews if any(kw in r.text for kw in keywords)][:3]
            aspects.append(
                ReviewAspect(
                    aspect=aspect,
                    sentiment=sentiment,
                    severity=severity,
                    frequency=min(1.0, hits / max(len(reviews), 1)),
                    recent_trend="stable",
                    evidence_examples=examples,
                    confidence=0.7,
                )
            )
        return aspects
