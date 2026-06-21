import logging
from datetime import datetime

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.semantic_frame import SemanticFrame
from tools.base import BaseTravelTool

logger = logging.getLogger(__name__)


class SeasonalityTool(BaseTravelTool):
    """Seasonal / best-time evidence — prefers climate data, not hard facts."""

    name = "seasonality"

    def __init__(self, weather_tool=None, knowledge_prior_tool=None) -> None:
        self._weather = weather_tool
        self._prior = knowledge_prior_tool

    async def run(
        self,
        city: str | None = None,
        country: str | None = None,
        place_name: str | None = None,
        semantic_frame: SemanticFrame | None = None,
        raw_query: str | None = None,
        **kwargs,
    ) -> list[Evidence]:
        frame = semantic_frame or kwargs.get("frame")
        if self._weather and city and country:
            try:
                weather_ev = await self._weather.run(
                    city=city,
                    country=country,
                    travel_date=kwargs.get("travel_date"),
                )
                if weather_ev:
                    for ev in weather_ev:
                        for claim in ev.claims:
                            if claim.claim_type in {ClaimType.WEATHER, ClaimType.SEASONALITY}:
                                return weather_ev
            except Exception as exc:
                logger.warning("SeasonalityTool weather branch failed: %s", exc)

        target = place_name or city or country or "目的地"
        summary = (
            f"{target} 的季节性旅行信息需结合当年气候与节庆；"
            "建议同时查阅目的地旅游局或气候资料以确认最佳月份。"
        )
        return [
            Evidence(
                source_name="Seasonality Advisory",
                source_type=SourceType.MODEL_PRIOR,
                country=country,
                city=city,
                place_name=place_name,
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.STALE,
                license_scope=LicenseScope.UNKNOWN,
                confidence=0.45,
                claims=[
                    Claim(
                        claim_type=ClaimType.SEASONALITY,
                        value=summary,
                        confidence=0.45,
                    )
                ],
                limitations=["季节性工具提供一般性参考，非实时官方数据。"],
            )
        ]
