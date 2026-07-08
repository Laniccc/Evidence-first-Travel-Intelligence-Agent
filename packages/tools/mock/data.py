"""Curated mock place data for MVP demo across Japan, China, South Korea."""

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType

PLACE_ALIASES = {
    "清水寺": "Kiyomizu-dera",
    "kiyomizu": "Kiyomizu-dera",
    "伏见稻荷": "Fushimi Inari",
    "fushimi inari": "Fushimi Inari",
    "岚山竹林": "Arashiyama Bamboo Grove",
    "岚山": "Arashiyama Bamboo Grove",
    "故宫": "Forbidden City",
    "紫禁城": "Forbidden City",
    "forbidden city": "Forbidden City",
    "颐和园": "Summer Palace",
    "天坛": "Temple of Heaven",
    "景福宫": "Gyeongbokgung Palace",
    "gyeongbokgung": "Gyeongbokgung Palace",
    "北村韩屋村": "Bukchon Hanok Village",
    "bukchon": "Bukchon Hanok Village",
    "南山塔": "N Seoul Tower",
    "n seoul tower": "N Seoul Tower",
    "明洞": "Myeongdong",
    "新宿": "Shinjuku",
}

PLACE_REGISTRY = {
    "Kiyomizu-dera": {
        "country": "Japan",
        "city": "Kyoto",
        "category": "temple",
        "address": "1-294 Kiyomizu, Higashiyama Ward, Kyoto",
        "official_url": "https://www.kiyomizudera.or.jp/en/",
        "opening_hours": "06:00-18:00 (seasonal variation possible)",
        "ticket_price": "400 JPY",
        "reservation": "No advance reservation required for general visit",
        "transit": "Bus to Gojo-zaka or Kiyomizu-michi, then 10-15 min uphill walk",
        "walking_intensity": 0.72,
        "elderly_friendliness": 0.45,
        "crowd_risk": 0.78,
        "transport_convenience": 0.62,
        "first_timer_fit": 0.92,
        "photo_experience": 0.88,
        "accessibility": 0.35,
    },
    "Fushimi Inari": {
        "country": "Japan",
        "city": "Kyoto",
        "category": "shrine",
        "address": "68 Fukakusa Yabunouchicho, Fushimi Ward, Kyoto",
        "official_url": "https://inari.jp/en/",
        "opening_hours": "Open 24 hours",
        "ticket_price": "Free",
        "reservation": "Not required",
        "transit": "JR Inari Station or Keihan Fushimi-Inari, short walk",
        "walking_intensity": 0.85,
        "elderly_friendliness": 0.35,
        "crowd_risk": 0.82,
        "transport_convenience": 0.88,
        "first_timer_fit": 0.85,
        "photo_experience": 0.9,
        "accessibility": 0.4,
    },
    "Arashiyama Bamboo Grove": {
        "country": "Japan",
        "city": "Kyoto",
        "category": "nature",
        "address": "Sagaogurayama Tabuchiyamacho, Ukyo Ward, Kyoto",
        "official_url": "https://www.city.kyoto.lg.jp/",
        "opening_hours": "Always open (path access)",
        "ticket_price": "Free",
        "reservation": "Not required",
        "transit": "JR Saga-Arashiyama or Hankyu Arashiyama, then walk",
        "walking_intensity": 0.55,
        "elderly_friendliness": 0.58,
        "crowd_risk": 0.75,
        "transport_convenience": 0.7,
        "first_timer_fit": 0.8,
        "photo_experience": 0.82,
        "accessibility": 0.5,
    },
    "Forbidden City": {
        "country": "China",
        "city": "Beijing",
        "category": "historical",
        "address": "4 Jingshan Front St, Dongcheng, Beijing",
        "official_url": "https://www.dpm.org.cn/",
        "opening_hours": "08:30-17:00 (closed Monday except holidays)",
        "ticket_price": "60 CNY peak season",
        "reservation": "Real-name online reservation required",
        "transit": "Metro Line 1 Tiananmen East/West, walk 10-15 min",
        "walking_intensity": 0.8,
        "elderly_friendliness": 0.4,
        "crowd_risk": 0.9,
        "transport_convenience": 0.85,
        "first_timer_fit": 0.95,
        "photo_experience": 0.85,
        "accessibility": 0.45,
    },
    "Summer Palace": {
        "country": "China",
        "city": "Beijing",
        "category": "garden",
        "address": "19 Xinjiangongmen Rd, Haidian, Beijing",
        "official_url": "https://www.summerpalace-china.com/",
        "opening_hours": "06:30-18:00 (seasonal variation)",
        "ticket_price": "30 CNY (park), combo tickets vary",
        "reservation": "Online booking recommended on peak days",
        "transit": "Metro Line 4 Beigongmen, walk 5-10 min",
        "walking_intensity": 0.65,
        "elderly_friendliness": 0.55,
        "crowd_risk": 0.7,
        "transport_convenience": 0.78,
        "first_timer_fit": 0.82,
        "photo_experience": 0.8,
        "accessibility": 0.55,
    },
    "Temple of Heaven": {
        "country": "China",
        "city": "Beijing",
        "category": "historical",
        "address": "1 Tiantan East Rd, Dongcheng, Beijing",
        "official_url": "https://www.tiantanpark.com/",
        "opening_hours": "06:00-22:00 park; hall hours shorter",
        "ticket_price": "15 CNY park, hall tickets extra",
        "reservation": "Online reservation recommended",
        "transit": "Metro Line 5 Tiantan Dongmen",
        "walking_intensity": 0.6,
        "elderly_friendliness": 0.6,
        "crowd_risk": 0.65,
        "transport_convenience": 0.8,
        "first_timer_fit": 0.78,
        "photo_experience": 0.75,
        "accessibility": 0.58,
    },
    "Gyeongbokgung Palace": {
        "country": "South Korea",
        "city": "Seoul",
        "category": "palace",
        "address": "161 Sajik-ro, Jongno-gu, Seoul",
        "official_url": "https://www.royalpalace.go.kr/",
        "opening_hours": "09:00-18:00 (closed Tuesday)",
        "ticket_price": "3,000 KRW",
        "reservation": "Not required; free entry in hanbok per policy periods",
        "transit": "Metro Line 3 Gyeongbokgung Station Exit 5, 5 min walk",
        "walking_intensity": 0.5,
        "elderly_friendliness": 0.62,
        "crowd_risk": 0.68,
        "transport_convenience": 0.88,
        "first_timer_fit": 0.9,
        "photo_experience": 0.86,
        "accessibility": 0.6,
    },
    "Bukchon Hanok Village": {
        "country": "South Korea",
        "city": "Seoul",
        "category": "cultural district",
        "address": "Gyedong-gil, Jongno-gu, Seoul",
        "official_url": "https://www.visitseoul.net/",
        "opening_hours": "Outdoor area always accessible; respect residential quiet hours",
        "ticket_price": "Free",
        "reservation": "Not required",
        "transit": "Metro Line 3 Anguk Station, 5-10 min walk on slopes",
        "walking_intensity": 0.68,
        "elderly_friendliness": 0.48,
        "crowd_risk": 0.72,
        "transport_convenience": 0.82,
        "first_timer_fit": 0.84,
        "photo_experience": 0.88,
        "accessibility": 0.42,
    },
    "N Seoul Tower": {
        "country": "South Korea",
        "city": "Seoul",
        "category": "viewpoint",
        "address": "105 Namsangongwon-gil, Yongsan-gu, Seoul",
        "official_url": "https://www.nseoultower.co.kr/",
        "opening_hours": "10:00-23:00 (observatory hours vary)",
        "ticket_price": "21,000 KRW observatory (approx.)",
        "reservation": "Optional online ticket",
        "transit": "Namsan cable car or bus, then walk/transfer",
        "walking_intensity": 0.55,
        "elderly_friendliness": 0.58,
        "crowd_risk": 0.7,
        "transport_convenience": 0.65,
        "first_timer_fit": 0.75,
        "photo_experience": 0.92,
        "accessibility": 0.65,
    },
}

CITY_COUNTRY = {
    "kyoto": ("Japan", "Kyoto"),
    "tokyo": ("Japan", "Tokyo"),
    "osaka": ("Japan", "Osaka"),
    "beijing": ("China", "Beijing"),
    "shanghai": ("China", "Shanghai"),
    "seoul": ("South Korea", "Seoul"),
    "busan": ("South Korea", "Busan"),
    "sapporo": ("Japan", "Sapporo"),
    "札幌": ("Japan", "Sapporo"),
    "okayama": ("Japan", "Okayama"),
    "冈山": ("Japan", "Okayama"),
    "chengdu": ("China", "Chengdu"),
    "成都": ("China", "Chengdu"),
    "hemu": ("China", "Altay"),
    "禾木": ("China", "Altay"),
    "禾木景区": ("China", "Altay"),
    "kanas": ("China", "Altay"),
    "喀纳斯": ("China", "Altay"),
    "喀纳斯湖": ("China", "Altay"),
    "新疆": ("China", "Altay"),
    "阿勒泰": ("China", "Altay"),
    "altay": ("China", "Altay"),
}

LOCATION_ALIASES = {
    "新宿": ("Japan", "Tokyo", "Shinjuku"),
    "shinjuku": ("Japan", "Tokyo", "Shinjuku"),
    "明洞": ("South Korea", "Seoul", "Myeongdong"),
    "myeongdong": ("South Korea", "Seoul", "Myeongdong"),
    "北京": ("China", "Beijing", "Beijing"),
    "上海": ("China", "Shanghai", "Shanghai"),
    "禾木": ("China", "Altay", "Hemu"),
    "禾木景区": ("China", "Altay", "Hemu"),
    "喀纳斯": ("China", "Altay", "Kanas Lake"),
    "喀纳斯湖": ("China", "Altay", "Kanas Lake"),
}

MOCK_REVIEWS = {
    "Kiyomizu-dera": [
        {"source": "Tripadvisor", "rating": 4.5, "text": "Beautiful temple but very crowded after 10am. Steep uphill walk from bus stop.", "language": "en"},
        {"source": "Google Maps", "rating": 4.6, "text": "Iconic Kyoto spot. Elderly in our group needed frequent rest due to slopes.", "language": "en"},
        {"source": "本地评价", "rating": 4.3, "text": "坡道较多，周末旅行团密集，建议早上去。", "language": "zh"},
    ],
    "Fushimi Inari": [
        {"source": "Tripadvisor", "rating": 4.7, "text": "Amazing torii gates but full hike is long and tiring for seniors.", "language": "en"},
        {"source": "Google Maps", "rating": 4.8, "text": "Crowded near entrance. Go early for photos.", "language": "en"},
    ],
    "Arashiyama Bamboo Grove": [
        {"source": "Tripadvisor", "rating": 4.2, "text": "Small area but scenic. Very crowded midday.", "language": "en"},
        {"source": "Google Maps", "rating": 4.4, "text": "Easy walk compared to temple hills. Combine with river area.", "language": "en"},
    ],
    "Forbidden City": [
        {"source": "大众点评", "rating": 4.7, "text": "必须提前预约，节假日人流极大，走路很多。", "language": "zh"},
        {"source": "Tripadvisor", "rating": 4.6, "text": "Must-see but exhausting. Reservation system is strict.", "language": "en"},
    ],
    "Summer Palace": [
        {"source": "大众点评", "rating": 4.6, "text": "园林漂亮，比故宫轻松一些，周末仍较拥挤。", "language": "zh"},
    ],
    "Temple of Heaven": [
        {"source": "大众点评", "rating": 4.5, "text": "公园面积大但主殿区域需要额外购票，早晨本地人多。", "language": "zh"},
    ],
    "Gyeongbokgung Palace": [
        {"source": "Tripadvisor", "rating": 4.5, "text": "Great first palace in Seoul. Changing guard can be crowded.", "language": "en"},
        {"source": "Naver Reviews", "rating": 4.4, "text": "Closed Tuesday. Easy metro access.", "language": "ko"},
    ],
    "Bukchon Hanok Village": [
        {"source": "Tripadvisor", "rating": 4.3, "text": "Pretty alleys but hilly. Not ideal for mobility issues.", "language": "en"},
    ],
    "N Seoul Tower": [
        {"source": "Tripadvisor", "rating": 4.4, "text": "Romantic night views. Queue for cable car can be long.", "language": "en"},
    ],
}


def normalize_place_name(name: str) -> str | None:
    key = name.strip()
    lower = key.lower()
    if key in PLACE_ALIASES:
        return PLACE_ALIASES[key]
    if lower in PLACE_ALIASES:
        return PLACE_ALIASES[lower]
    for canonical, meta in PLACE_REGISTRY.items():
        if lower == canonical.lower() or key == canonical:
            return canonical
    return None


def find_places_in_text(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for alias, canonical in PLACE_ALIASES.items():
        if alias.lower() in lower and canonical not in found:
            found.append(canonical)
    for canonical in PLACE_REGISTRY:
        if canonical.lower() in lower and canonical not in found:
            found.append(canonical)
    return found


def get_place_location(place_name: str) -> tuple[str, str] | None:
    canonical = normalize_place_name(place_name) or place_name
    meta = PLACE_REGISTRY.get(canonical)
    if not meta:
        return None
    return meta["country"], meta["city"]


def registered_places_for_city(country: str, city: str) -> list[str]:
    return [name for name, meta in PLACE_REGISTRY.items() if meta["country"] == country and meta["city"] == city]


def registered_places_for_country(country: str) -> list[str]:
    return [name for name, meta in PLACE_REGISTRY.items() if meta["country"] == country]


def build_official_evidence(place_name: str) -> Evidence | None:
    meta = PLACE_REGISTRY.get(place_name)
    if not meta:
        return None
    return Evidence(
        source_name=f"{place_name} Official Site (Mock)",
        source_type=SourceType.OFFICIAL,
        source_url=meta["official_url"],
        country=meta["country"],
        city=meta["city"],
        place_name=place_name,
        data_freshness=DataFreshness.RECENT,
        license_scope=LicenseScope.PUBLIC_PAGE,
        confidence=0.92,
        claims=[
            Claim(claim_type=ClaimType.OPENING_HOURS, value=meta["opening_hours"], normalized_value=meta["opening_hours"], confidence=0.95),
            Claim(claim_type=ClaimType.TICKET_PRICE, value=meta["ticket_price"], normalized_value=meta["ticket_price"], confidence=0.9),
            Claim(claim_type=ClaimType.RESERVATION, value=meta["reservation"], normalized_value=meta["reservation"], confidence=0.9),
            Claim(claim_type=ClaimType.ADDRESS, value=meta["address"], normalized_value=meta["address"], confidence=0.95),
            Claim(claim_type=ClaimType.SAFETY, value=meta["walking_intensity"], normalized_value=meta["walking_intensity"], confidence=0.72),
        ],
    )


def build_map_evidence(place_name: str) -> Evidence | None:
    meta = PLACE_REGISTRY.get(place_name)
    if not meta:
        return None
    return Evidence(
        source_name="Google Maps (Mock)",
        source_type=SourceType.MAP,
        source_url="https://maps.google.com/",
        country=meta["country"],
        city=meta["city"],
        place_name=place_name,
        confidence=0.85,
        claims=[
            Claim(claim_type=ClaimType.ADDRESS, value=meta["address"], confidence=0.9),
            Claim(claim_type=ClaimType.CROWD, value=meta["crowd_risk"], normalized_value=meta["crowd_risk"], confidence=0.75),
            Claim(claim_type=ClaimType.ACCESSIBILITY, value=meta["accessibility"], normalized_value=meta["accessibility"], confidence=0.7),
        ],
    )


def build_transit_evidence(place_name: str) -> Evidence | None:
    meta = PLACE_REGISTRY.get(place_name)
    if not meta:
        return None
    return Evidence(
        source_name="Transit API (Mock)",
        source_type=SourceType.TRANSIT_API,
        source_url="https://mock-transit.local/",
        country=meta["country"],
        city=meta["city"],
        place_name=place_name,
        confidence=0.8,
        claims=[
            Claim(claim_type=ClaimType.TRANSIT, value=meta["transit"], normalized_value=meta["transit"], confidence=0.82),
            Claim(claim_type=ClaimType.TRANSIT, value=meta["transport_convenience"], normalized_value=meta["transport_convenience"], confidence=0.78),
        ],
    )


def build_weather_evidence(city: str, country: str, travel_date: str | None) -> Evidence:
    date_note = travel_date or "upcoming day"
    return Evidence(
        source_name="Weather API (Mock)",
        source_type=SourceType.WEATHER_API,
        source_url="https://mock-weather.local/",
        country=country,
        city=city,
        confidence=0.88,
        claims=[
            Claim(
                claim_type=ClaimType.WEATHER,
                value=f"Partly cloudy, 24-29C, low rain risk for {date_note}",
                normalized_value={"condition": "partly_cloudy", "rain_risk": 0.15, "temp_high": 29, "temp_low": 24},
                confidence=0.86,
            )
        ],
        limitations=["Mock weather data; verify before departure."],
    )


def build_review_evidence(place_name: str) -> Evidence | None:
    reviews = MOCK_REVIEWS.get(place_name, [])
    if not reviews:
        return None
    meta = PLACE_REGISTRY[place_name]
    return Evidence(
        source_name="Review Platform (Mock)",
        source_type=SourceType.REVIEW_PLATFORM,
        source_url="https://mock-reviews.local/",
        country=meta["country"],
        city=meta["city"],
        place_name=place_name,
        confidence=0.78,
        claims=[
            Claim(
                claim_type=ClaimType.REVIEW_ASPECT,
                value=reviews,
                normalized_value={"review_count": len(reviews), "avg_rating": round(sum(r["rating"] for r in reviews) / len(reviews), 2)},
                confidence=0.75,
            )
        ],
        limitations=["Only review summaries stored, not full licensed text."],
    )
