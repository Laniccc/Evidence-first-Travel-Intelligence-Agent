from app.schemas.evidence import Evidence
from app.tools.base import BaseTool
from app.tools.mock_data import build_weather_evidence


class MockWeatherTool(BaseTool):
    name = "mock_weather"

    async def run(self, city: str, country: str, travel_date: str | None = None, **kwargs) -> list[Evidence]:
        return [build_weather_evidence(city, country, travel_date)]
