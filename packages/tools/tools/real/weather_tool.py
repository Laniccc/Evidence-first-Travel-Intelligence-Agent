import logging
from datetime import datetime, timedelta

import httpx

from app.config import get_settings
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool

logger = logging.getLogger(__name__)

_COUNTRY_CODES = {
    "Japan": "JP",
    "China": "CN",
    "South Korea": "KR",
}


class RealWeatherTool(BaseTravelTool):
    name = "real_weather_tool"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_real_weather and settings.weather_api_key)

    async def run(
        self,
        city: str,
        country: str,
        travel_date: str | None = None,
        date: str | None = None,
        coordinates: tuple[float, float] | None = None,
        **kwargs,
    ) -> list[Evidence]:
        settings = get_settings()
        if not self.is_available():
            raise RuntimeError("WEATHER_API_KEY missing or ENABLE_REAL_WEATHER=false")

        target_date = travel_date or date
        lat, lon = coordinates if coordinates else await self._geocode(city, country, settings.weather_api_key)
        forecast = await self._fetch_forecast(lat, lon, settings.weather_api_key)

        slot = self._pick_slot(forecast, target_date)
        if not slot:
            raise RuntimeError("No forecast data for requested date")

        temp_min = slot.get("main", {}).get("temp_min")
        temp_max = slot.get("main", {}).get("temp_max")
        weather_main = slot.get("weather", [{}])[0].get("main", "Unknown")
        weather_desc = slot.get("weather", [{}])[0].get("description", weather_main)
        pop = float(slot.get("pop", 0.0))
        weather_risk = "high" if pop >= 0.6 or weather_main.lower() in {"thunderstorm", "snow", "rain"} else (
            "medium" if pop >= 0.3 else "low"
        )

        retrieved_at = datetime.utcnow()
        confidence = 0.82 if target_date else 0.78
        freshness = DataFreshness.LIVE if not target_date else DataFreshness.RECENT

        evidence = Evidence(
            source_name="OpenWeatherMap",
            source_type=SourceType.WEATHER_API,
            source_url="https://openweathermap.org/",
            country=country,
            city=city,
            retrieved_at=retrieved_at,
            data_freshness=freshness,
            license_scope=LicenseScope.API_ALLOWED,
            confidence=confidence,
            claims=[
                Claim(
                    claim_type=ClaimType.WEATHER,
                    value=weather_desc,
                    normalized_value={
                        "weather": weather_main,
                        "condition": weather_desc,
                        "temperature_range": {"min_c": temp_min, "max_c": temp_max},
                        "precipitation_probability": pop,
                        "weather_risk": weather_risk,
                        "retrieved_at": retrieved_at.isoformat(),
                        "source_type": SourceType.WEATHER_API.value,
                        "data_freshness": freshness.value,
                        "confidence": confidence,
                    },
                    confidence=confidence,
                ),
            ],
            limitations=[],
        )
        return [evidence]

    async def _geocode(self, city: str, country: str, api_key: str) -> tuple[float, float]:
        country_code = _COUNTRY_CODES.get(country, "")
        query = f"{city},{country_code}" if country_code else city
        url = "https://api.openweathermap.org/geo/1.0/direct"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params={"q": query, "limit": 1, "appid": api_key})
            resp.raise_for_status()
            data = resp.json()
            if not data:
                raise RuntimeError(f"Geocoding failed for {query}")
            return float(data[0]["lat"]), float(data[0]["lon"])

    async def _fetch_forecast(self, lat: float, lon: float, api_key: str) -> list[dict]:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                url,
                params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            )
            resp.raise_for_status()
            return resp.json().get("list", [])

    def _pick_slot(self, forecast: list[dict], target_date: str | None) -> dict | None:
        if not forecast:
            return None
        if not target_date:
            return forecast[0]
        try:
            target = datetime.fromisoformat(target_date.replace("Z", "")).date()
        except ValueError:
            return forecast[0]
        for slot in forecast:
            dt = datetime.utcfromtimestamp(slot["dt"])
            if dt.date() == target:
                return slot
        return forecast[0]
