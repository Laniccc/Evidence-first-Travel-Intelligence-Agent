"""Official source discovery tool — S5 candidate extraction."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.official_source import OfficialSourceDiscoveryResult
from tools.base import BaseTravelTool
from tools.official_source.official_source_classifier import OfficialSourceClassifier
from tools.official_source.url_normalizer import (
    dedupe_hits,
    extract_domain,
    hits_from_evidence_list,
    is_fetchable_url,
    is_search_task_metadata,
    normalize_search_hit,
)
from tools.official_source.whitelist_resolver import resolve_official_whitelist_url

logger = logging.getLogger(__name__)


class OfficialSourceDiscoveryTool(BaseTravelTool):
    name = "official_source_discovery_mcp"
    policy_name = "official_source_discovery_mcp"

    def __init__(self) -> None:
        self.classifier = OfficialSourceClassifier()
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(getattr(settings, "official_source_discovery_enabled", True))

    async def run(self, **kwargs) -> list[Evidence]:
        self.last_run_meta = {}
        if not self.is_configured():
            self.last_run_meta = {
                "error": "official_source_discovery disabled",
                "official_source_discovery": True,
                "urls_checked_count": 0,
                "official_candidates_count": 0,
                "top_source_classes": [],
            }
            return []

        place_name = str(kwargs.get("place_name") or "").strip() or "目的地"
        claim_type = kwargs.get("claim_type") or kwargs.get("information_need")
        city = kwargs.get("city")
        country = kwargs.get("country") or "Unknown"
        max_candidates = int(kwargs.get("max_candidates") or 8)
        probe_top_n = kwargs.get("probe_top_n")
        if probe_top_n is None:
            probe_top_n = 1
        else:
            probe_top_n = int(probe_top_n)

        hits = self._collect_hits(kwargs)
        limitations: list[str] = []
        if not hits:
            self._set_meta(0, 0, [])
            return []

        anchor_terms = list(kwargs.get("anchor_terms") or kwargs.get("aliases") or [])
        ticket_product = kwargs.get("ticket_product")
        try:
            from app.orchestrator.ticket_relevance_policy import discovery_hit_relevant

            filtered = [
                h
                for h in hits
                if discovery_hit_relevant(
                    h,
                    place_name=place_name,
                    claim_type=str(claim_type) if claim_type else None,
                    anchor_terms=anchor_terms,
                    ticket_product=str(ticket_product) if ticket_product else None,
                )
            ]
            if not filtered and hits:
                limitations.append("skipped_reason=no_relevant_urls")
                self._set_meta(0, 0, [])
                return []
            hits = filtered
        except ImportError:
            pass

        candidates = []
        seen_urls: set[str] = set()
        for hit in hits:
            normalized = normalize_search_hit(hit)
            if not normalized:
                continue
            url = normalized.get("url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            candidate = self.classifier.classify(
                url or f"snippet://{normalized.get('title') or 'unknown'}",
                title=normalized.get("title"),
                snippet=normalized.get("snippet"),
                place_name=place_name,
                city=city,
                claim_type=claim_type,
                discovered_by=self.name,
            )
            candidates.append(candidate)
            if len(candidates) >= max_candidates:
                break

        if probe_top_n > 0:
            await self._probe_top_candidates(candidates[:probe_top_n], place_name=place_name, claim_type=claim_type)

        candidates.sort(key=lambda c: c.official_confidence, reverse=True)
        result = OfficialSourceDiscoveryResult(
            place_name=place_name,
            claim_type=claim_type,
            candidates=candidates,
            search_queries_used=list(kwargs.get("search_queries_used") or []),
            limitations=limitations,
        )

        evidence_list = self._candidates_to_evidence(
            result,
            country=country,
            city=city,
        )
        top_classes = [c.source_class for c in candidates[:5]]
        self._set_meta(len(hits), len(candidates), top_classes)
        return evidence_list

    def _collect_hits(self, kwargs: dict) -> list[dict]:
        hits: list[dict] = []
        place_name = str(kwargs.get("place_name") or "").strip()

        whitelist_url = resolve_official_whitelist_url(place_name)
        if whitelist_url:
            hits.append(
                {
                    "url": whitelist_url,
                    "title": f"{place_name} 官网",
                    "snippet": None,
                }
            )

        prior = kwargs.get("prior_evidence") or kwargs.get("evidence") or []
        if isinstance(prior, list):
            hits.extend(hits_from_evidence_list(prior))

        for item in kwargs.get("search_results") or []:
            if not isinstance(item, dict) or is_search_task_metadata(item):
                continue
            normalized = normalize_search_hit(item)
            if normalized:
                hits.append(normalized)

        for url in kwargs.get("urls") or []:
            if url:
                hits.append({"url": str(url), "title": None, "snippet": None})

        return dedupe_hits(hits)

    async def _probe_top_candidates(
        self,
        candidates: list,
        *,
        place_name: str,
        claim_type: str | None,
    ) -> None:
        from tools.mcp.adapters.official_page_fetch_adapter import OfficialPageFetchAdapter
        from tools.mcp.adapters.page_content_extractor import normalize_page_text

        adapter = OfficialPageFetchAdapter()
        for cand in candidates:
            if not is_fetchable_url(cand.url):
                cand.limitations.append("Skipped page probe: non-fetchable redirect URL.")
                continue
            try:
                pages = await adapter.run(
                    url=cand.url,
                    place_name=place_name,
                    information_need=claim_type,
                    max_follow_urls=3,
                )
                if not pages:
                    continue
                page = pages[0]
                text = " ".join(
                    str(c.raw_text or c.value)
                    for c in page.claims
                    if str(c.value).strip()
                )
                excerpt = normalize_page_text(text)[:1200]
                refreshed = self.classifier.classify(
                    page.source_url or cand.url,
                    title=cand.title,
                    snippet=cand.page_excerpt,
                    page_excerpt=excerpt,
                    place_name=place_name,
                    claim_type=claim_type,
                    discovered_by=self.name,
                )
                refreshed.verified_by = "official_page_reader_mcp"
                if page.source_url and page.source_url != cand.url:
                    refreshed.url = page.source_url
                    refreshed.domain = extract_domain(page.source_url)
                    refreshed.limitations.append(f"Followed official subpage: {page.source_url}")
                cand.__dict__.update(refreshed.model_dump())
            except Exception as exc:
                logger.debug("probe failed for %s: %s", cand.url, exc)
                cand.limitations.append(f"Page probe failed: {exc}")

    def _candidates_to_evidence(
        self,
        result: OfficialSourceDiscoveryResult,
        *,
        country: str,
        city: str | None,
    ) -> list[Evidence]:
        if not result.candidates:
            return self._limitation_evidence(
                result.place_name,
                country=country,
                city=city,
                claim_type=result.claim_type,
                limitations=result.limitations or ["No official source candidates identified."],
            )

        out: list[Evidence] = []
        for cand in result.candidates:
            summary = (
                f"Official source candidate ({cand.source_class}, "
                f"confidence={cand.official_confidence:.2f}): {cand.title or cand.domain}"
            )
            out.append(
                Evidence(
                    source_name="Official Source Discovery",
                    source_type=SourceType.WEB,
                    source_url=cand.url if is_fetchable_url(cand.url) else None,
                    country=country,
                    city=city,
                    place_name=result.place_name,
                    retrieved_at=datetime.utcnow(),
                    data_freshness=DataFreshness.RECENT,
                    license_scope=LicenseScope.PUBLIC_PAGE,
                    confidence=cand.official_confidence,
                    claims=[
                        Claim(
                            claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                            value=summary,
                            raw_text=summary,
                            normalized_value=cand.model_dump(),
                            confidence=cand.official_confidence,
                        )
                    ],
                    limitations=list(cand.limitations),
                )
            )
        return out

    def _limitation_evidence(
        self,
        place_name: str,
        *,
        country: str,
        city: str | None,
        claim_type: str | None,
        limitations: list[str],
    ) -> list[Evidence]:
        return [
            Evidence(
                source_name="Official Source Discovery",
                source_type=SourceType.WEB,
                source_url=None,
                country=country,
                city=city,
                place_name=place_name,
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.RECENT,
                license_scope=LicenseScope.PUBLIC_PAGE,
                confidence=0.35,
                claims=[
                    Claim(
                        claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                        value="No official source candidates found.",
                        raw_text=json.dumps({"claim_type": claim_type, "limitations": limitations}, ensure_ascii=False),
                        confidence=0.35,
                    )
                ],
                limitations=limitations,
            )
        ]

    def _set_meta(self, urls_checked: int, candidates_count: int, top_classes: list[str]) -> None:
        self.last_run_meta = {
            "official_source_discovery": True,
            "urls_checked_count": urls_checked,
            "official_candidates_count": candidates_count,
            "top_source_classes": top_classes,
            "output_parse_status": "ok",
        }
