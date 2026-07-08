"""Composite crowd estimation from Ctrip heat, Dianping queue signals, and Baidu traffic."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.config import Settings, get_settings
from tools.crawlers.ctrip_crawler_tool import CtripReviewCrawlerTool
from tools.crawlers.dianping_crawler_tool import DianpingReviewCrawlerTool
from tools.ticketing.evidence_normalizer import normalize_crowd_estimation_payload
from tools.ticketing.provider_config import crowd_estimation_configured


_CROWD_WORDS = re.compile(r"人多|拥挤|爆满|排队|人山人海")
_CALM_WORDS = re.compile(r"人少|清净|空旷|不挤")


class CrowdEstimationTool:
    policy_name = "crowd_estimation_mcp"
    provider_name = "CrowdEstimation"

    def __init__(self, settings: Settings | None = None, registry: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._registry = registry
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return crowd_estimation_configured(self.settings)

    @staticmethod
    def _score_from_evidence(evidence: list) -> tuple[float, str | None]:
        score = 0.45
        detail: str | None = None
        for ev in evidence:
            for claim in ev.claims:
                text = str(claim.value)
                if _CROWD_WORDS.search(text):
                    score += 0.15
                    detail = text[:120]
                if _CALM_WORDS.search(text):
                    score -= 0.1
                heat_match = re.search(r"heat_score:\s*([\d.]+)", text)
                if heat_match:
                    try:
                        heat = float(heat_match.group(1))
                        score = max(score, min(0.95, heat / 10.0))
                    except ValueError:
                        pass
        score = max(0.1, min(0.95, score))
        label = "high" if score >= 0.7 else "medium" if score >= 0.45 else "low"
        return score, detail

    async def _ctrip_signal(self, place_name: str, city: str | None, country: str) -> list:
        tool = CtripReviewCrawlerTool(self.settings)
        tool.crawler_mode = "crowd"
        if not tool.is_configured():
            return []
        return await tool.run(place_name=place_name, city=city, country=country, claim_type="current_crowd_estimate")

    async def _dianping_signal(self, place_name: str, city: str | None, country: str) -> list:
        tool = DianpingReviewCrawlerTool(self.settings)
        if not tool.is_configured():
            return []
        return await tool.run(place_name=place_name, city=city, country=country, claim_type="queue_risk")

    async def _baidu_traffic_signal(self, place_name: str, city: str | None) -> list:
        registry = self._registry
        if registry is None:
            return []
        traffic_tool = getattr(registry, "baidu_traffic_mcp", None)
        if traffic_tool is None:
            return []
        query = f"{city or ''} {place_name}".strip()
        try:
            return await traffic_tool.run(
                place_name=place_name,
                city=city,
                query=query,
                road_name=query,
            )
        except Exception:
            return []

    async def run(
        self,
        *,
        place_name: str,
        city: str | None = None,
        country: str | None = "China",
        query: str | None = None,
        claim_type: str | None = None,
    ) -> list:
        effective_place = place_name or query or city or ""
        sources: list[str] = []
        merged: list = []

        ctrip_ev, dianping_ev, traffic_ev = await asyncio.gather(
            self._ctrip_signal(effective_place, city, country or "China"),
            self._dianping_signal(effective_place, city, country or "China"),
            self._baidu_traffic_signal(effective_place, city),
        )
        if ctrip_ev:
            sources.append("ctrip_crowd")
            merged.extend(ctrip_ev)
        if dianping_ev:
            sources.append("dianping_review")
            merged.extend(dianping_ev)
        if traffic_ev:
            sources.append("baidu_traffic")
            merged.extend(traffic_ev)

        if not merged:
            self.last_run_meta = {
                "provider": self.provider_name,
                "configured": self.is_configured(),
                "output_parse_status": "no_hits",
                "error": "no crowd signals available",
            }
            return []

        score, detail = self._score_from_evidence(merged)
        label = "high" if score >= 0.7 else "medium" if score >= 0.45 else "low"
        result = normalize_crowd_estimation_payload(
            place_name=effective_place,
            city=city,
            country=country or "China",
            score=score,
            label=label,
            sources=sources,
            detail=detail,
        )
        self.last_run_meta = {
            "provider": self.provider_name,
            "configured": True,
            "transport": "composite",
            "output_parse_status": "ok",
            "sources": sources,
            "crowd_score": score,
            "crowd_label": label,
        }
        return result
