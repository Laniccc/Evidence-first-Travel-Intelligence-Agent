import logging
from datetime import datetime

import httpx

from app.config import get_settings
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mock_data import normalize_place_name

logger = logging.getLogger(__name__)


class RealPlacesTool(BaseTravelTool):
    name = "real_places_tool"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_real_places and settings.places_api_key)

    async def run(
        self,
        place_name: str,
        country: str | None = None,
        city: str | None = None,
        **kwargs,
    ) -> list[Evidence]:
        settings = get_settings()
        if not self.is_available():
            raise RuntimeError("PLACES_API_KEY missing or ENABLE_REAL_PLACES=false")

        canonical = normalize_place_name(place_name) or place_name
        query_parts = [canonical]
        if city:
            query_parts.append(city)
        if country:
            query_parts.append(country)
        query = ", ".join(query_parts)

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": "EvidenceFirstTravelAgent/0.1 (pilot)"},
            )
            resp.raise_for_status()
            results = resp.json()

        limitations: list[str] = []
        if not results:
            raise RuntimeError(f"No places result for {query}")

        item = results[0]
        address = item.get("display_name")
        lat = item.get("lat")
        lon = item.get("lon")
        extratags = item.get("extratags") or {}

        normalized: dict = {
            "address": address,
            "coordinates": {"lat": lat, "lon": lon},
            "source_type": SourceType.MAP.value,
            "retrieved_at": None,
            "confidence": 0.72,
        }

        opening_status = extratags.get("opening_hours") or item.get("opening_hours")
        if opening_status:
            normalized["opening_status"] = opening_status
        else:
            limitations.append("opening_status not provided by API")

        rating = extratags.get("rating") or item.get("rating")
        if rating:
            normalized["rating"] = rating
        else:
            limitations.append("rating not provided by API")

        nearby_poi = kwargs.get("nearby_poi")
        if nearby_poi:
            normalized["nearby_poi"] = nearby_poi
        else:
            limitations.append("nearby_poi not provided by API")

        popular_times_proxy = extratags.get("popular_times") or extratags.get("tourism")
        if popular_times_proxy:
            normalized["popular_times_proxy"] = popular_times_proxy
        else:
            limitations.append("popular_times_proxy not provided by API")

        accessibility_proxy = extratags.get("wheelchair")
        if accessibility_proxy:
            normalized["accessibility_proxy"] = accessibility_proxy
        else:
            limitations.append("accessibility_proxy not provided by API")

        retrieved_at = __import__("datetime").datetime.utcnow()
        normalized["retrieved_at"] = retrieved_at.isoformat()
        confidence = 0.72

        evidence = Evidence(
            source_name="OpenStreetMap Nominatim",
            source_type=SourceType.MAP,
            source_url=f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}",
            country=country or "",
            city=city,
            place_name=canonical,
            retrieved_at=retrieved_at,
            data_freshness=DataFreshness.RECENT,
            license_scope=LicenseScope.PUBLIC_PAGE,
            confidence=confidence,
            claims=[
                Claim(
                    claim_type=ClaimType.ADDRESS,
                    value=address,
                    normalized_value=normalized,
                    confidence=confidence,
                ),
            ],
            limitations=limitations,
        )
        return [evidence]
