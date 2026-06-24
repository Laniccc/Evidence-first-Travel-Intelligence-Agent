"""Deterministic official source classifier."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.schemas.official_source import OfficialSourceCandidate
from tools.official_source.source_class_constants import (
    SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE,
    SOURCE_CLASS_MAP_PROVIDER_CANDIDATE,
    SOURCE_CLASS_NOT_OFFICIAL,
    SOURCE_CLASS_OFFICIAL_ACCOUNT_CANDIDATE,
    SOURCE_CLASS_OFFICIAL_GOVERNMENT,
    SOURCE_CLASS_OTA_PLATFORM,
    SOURCE_CLASS_REVIEW_PLATFORM,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
    SOURCE_CLASS_SEO_CONTENT_SITE,
    SOURCE_CLASS_THIRD_PARTY_PLATFORM,
    SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
    SOURCE_CLASS_UNKNOWN,
)
from tools.official_source.url_normalizer import (
    extract_domain,
    is_redirect_wrapper_url,
    place_name_in_text,
)

_GOV_DOMAIN_RE = re.compile(r"\.gov(\.cn)?$|gov\.cn$", re.I)
_TOURISM_HINTS = ("文旅", "旅游局", "文化和旅游", "tourism", "visit", "travel.gov")
_SCENIC_OPERATOR_HINTS = (
    "旅游开发",
    "景区管理",
    "风景名胜",
    "管委会",
    "运营有限公司",
    "旅游发展",
    "official site",
    "官方网站",
    "官网",
)
_OFFICIAL_TITLE_HINTS = ("官网", "官方网站", "管委会", "文旅局", "景区管理处", "游客服务")
_SEO_TITLE_HINTS = ("攻略", "门票预订", "旅游网", "游记", "排行榜", "预订", "点评")
_OTA_DOMAINS = (
    "ctrip.com",
    "trip.com",
    "fliggy.com",
    "dianping.com",
    "meituan.com",
    "qunar.com",
    "tuniu.com",
    "mafengwo.cn",
    "tripadvisor",
    "booking.com",
)
_REVIEW_DOMAINS = ("dianping.com", "tripadvisor", "mafengwo.cn", "xiaohongshu.com")
_MAP_DOMAINS = ("baidu.com", "amap.com", "autonavi.com", "google.com/maps", "lbsyun.baidu.com")
_SCENIC_OFFICIAL_DOMAINS = (
    "dpm.org.cn",
    "sanxingdui.org.cn",
    "potalapalace.cn",
)
_OFFICIAL_TITLE_PATTERNS = ("导览", "参观须知", "开放时间", "门票预约", "游客服务")
_TICKET_SNIPPET_RE = re.compile(r"门票|票价|收费|元/人|元每人|免费|维护费", re.I)
_HOURS_SNIPPET_RE = re.compile(r"开放时间|营业时间|开放时段|全天开放|开馆时间|闭馆时间|停止入馆", re.I)
_NOTICE_SNIPPET_RE = re.compile(r"公告|通知|闭园|暂停开放|临时关闭", re.I)
_CONTACT_SNIPPET_RE = re.compile(r"电话|投诉|游客中心|联系方式|tel", re.I)
_ABOUT_SNIPPET_RE = re.compile(r"关于我们|版权所有|备案|copyright|主体", re.I)


class OfficialSourceClassifier:
    """Score URL/title/snippet for official-source candidacy."""

    def classify(
        self,
        url: str,
        *,
        title: str | None = None,
        snippet: str | None = None,
        page_excerpt: str | None = None,
        place_name: str | None = None,
        city: str | None = None,
        claim_type: str | None = None,
        discovered_by: str | None = None,
    ) -> OfficialSourceCandidate:
        domain = extract_domain(url)
        blob = " ".join(filter(None, [title, snippet, page_excerpt, url]))
        score = 0.35
        supporting: list[str] = []
        negative: list[str] = []
        limitations: list[str] = []

        if is_redirect_wrapper_url(url):
            negative.append("redirect_wrapper_url")
            score -= 0.35
            limitations.append("Search redirect wrapper URL; not a direct official page.")

        if _GOV_DOMAIN_RE.search(domain) or any(h in blob for h in _TOURISM_HINTS):
            score += 0.35
            supporting.append("government_or_tourism_domain")

        if any(h in (title or "") for h in _OFFICIAL_TITLE_HINTS):
            score += 0.30
            supporting.append("official_title_hint")

        if place_name and place_name_in_text(place_name, title, snippet, page_excerpt):
            score += 0.25
            supporting.append("place_name_match")

        if any(h in blob for h in _SCENIC_OPERATOR_HINTS):
            score += 0.20
            supporting.append("scenic_operator_hint")

        text_for_fields = page_excerpt or snippet or ""
        has_ticket = bool(_TICKET_SNIPPET_RE.search(text_for_fields))
        has_hours = bool(_HOURS_SNIPPET_RE.search(text_for_fields))
        has_notice = bool(_NOTICE_SNIPPET_RE.search(text_for_fields))
        has_contact = bool(_CONTACT_SNIPPET_RE.search(text_for_fields))
        has_about = bool(_ABOUT_SNIPPET_RE.search(text_for_fields))

        if has_ticket:
            score += 0.20
            supporting.append("ticket_info_signal")
        if has_hours:
            score += 0.20
            supporting.append("opening_hours_signal")
        if has_notice:
            score += 0.15
            supporting.append("notice_signal")
        if has_contact:
            score += 0.15
            supporting.append("contact_signal")
        if has_about:
            score += 0.20
            supporting.append("about_or_footer_signal")

        if any(d in domain for d in _SCENIC_OFFICIAL_DOMAINS):
            score += 0.45
            supporting.append("known_scenic_official_domain")

        if is_redirect_wrapper_url(url) and place_name and place_name_in_text(place_name, title, snippet):
            if any(p in (title or "") for p in _OFFICIAL_TITLE_PATTERNS):
                score += 0.25
                supporting.append("official_title_on_redirect_hit")
            elif place_name in (title or "") and not any(h in (title or "") for h in _SEO_TITLE_HINTS):
                score += 0.15
                supporting.append("place_official_title_on_redirect")

        if any(d in domain for d in _OTA_DOMAINS):
            score -= 0.40
            negative.append("ota_domain")
        if any(d in domain for d in _REVIEW_DOMAINS):
            score -= 0.40
            negative.append("review_platform_domain")
        if any(d in domain for d in _MAP_DOMAINS):
            score -= 0.25
            negative.append("map_provider_domain")

        if any(h in (title or "") for h in _SEO_TITLE_HINTS):
            score -= 0.20
            negative.append("seo_title_hint")

        if not supporting and not place_name_in_text(place_name or "", title, snippet):
            score -= 0.30
            negative.append("weak_place_association")

        if "攻略" in (title or "") or "游记" in (title or ""):
            score -= 0.20
            negative.append("travel_guide_content")

        score = max(0.0, min(1.0, score))
        source_class = self._map_source_class(
            score,
            domain,
            blob,
            negative,
            place_name=place_name,
            title=title,
            snippet=snippet,
        )
        supports, relevance = self._supports_and_relevance(
            source_class,
            has_ticket=has_ticket,
            has_hours=has_hours,
            has_notice=has_notice,
            has_about=has_about,
        )

        org = self._guess_organization(title, domain, blob)
        return OfficialSourceCandidate(
            url=url,
            domain=domain,
            title=title,
            source_class=source_class,
            official_confidence=round(score, 3),
            organization_name=org,
            supports_claim_types=supports,
            supporting_signals=supporting,
            negative_signals=negative,
            limitations=limitations,
            discovered_by=discovered_by,
            page_excerpt=(page_excerpt or snippet or "")[:800] or None,
            has_ticket_info=has_ticket,
            has_opening_hours=has_hours,
            has_notice_info=has_notice,
            has_contact_info=has_contact,
            has_about_or_footer_info=has_about,
            claim_relevance_hints=relevance,
        )

    @staticmethod
    def _map_source_class(
        score: float,
        domain: str,
        blob: str,
        negative: list[str],
        *,
        place_name: str | None = None,
        title: str | None = None,
        snippet: str | None = None,
    ) -> str:
        if any(d in domain for d in _SCENIC_OFFICIAL_DOMAINS):
            return SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL
        if any(d in domain for d in _OTA_DOMAINS):
            return SOURCE_CLASS_OTA_PLATFORM
        if any(d in domain for d in _REVIEW_DOMAINS):
            return SOURCE_CLASS_REVIEW_PLATFORM
        if any(d in domain for d in _MAP_DOMAINS):
            return SOURCE_CLASS_MAP_PROVIDER_CANDIDATE
        if "redirect_wrapper_url" in negative:
            if score >= 0.55 and place_name_in_text(
                place_name or "", title, snippet
            ) and any(p in (title or snippet or "") for p in _OFFICIAL_TITLE_PATTERNS):
                return SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE
            return SOURCE_CLASS_SEO_CONTENT_SITE if score >= 0.35 else SOURCE_CLASS_NOT_OFFICIAL
        if _GOV_DOMAIN_RE.search(domain):
            if score >= 0.90:
                return SOURCE_CLASS_OFFICIAL_GOVERNMENT
            if any(h in blob for h in _TOURISM_HINTS):
                return SOURCE_CLASS_TOURISM_BOARD_OFFICIAL
            return SOURCE_CLASS_TOURISM_BOARD_OFFICIAL
        if score >= 0.80 and any(h in blob for h in _SCENIC_OPERATOR_HINTS):
            return SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL
        if score >= 0.65:
            return SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE
        if 0.55 <= score < 0.75 and ("ctrip" in domain or "ticket" in blob.lower()):
            return SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE
        if "weixin" in domain or "mp.weixin" in domain:
            return SOURCE_CLASS_OFFICIAL_ACCOUNT_CANDIDATE
        if score < 0.40:
            return SOURCE_CLASS_NOT_OFFICIAL
        if "攻略" in blob or "游记" in blob:
            return SOURCE_CLASS_SEO_CONTENT_SITE
        return SOURCE_CLASS_THIRD_PARTY_PLATFORM if score < 0.55 else SOURCE_CLASS_UNKNOWN

    @staticmethod
    def _supports_and_relevance(
        source_class: str,
        *,
        has_ticket: bool,
        has_hours: bool,
        has_notice: bool,
        has_about: bool,
    ) -> tuple[list[str], dict[str, float]]:
        supports: list[str] = []
        relevance: dict[str, float] = {}

        if source_class in {
            SOURCE_CLASS_OFFICIAL_GOVERNMENT,
            SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
        }:
            supports.append("destination_background")
            relevance["destination_background"] = 0.9
            if has_notice:
                supports.extend(["seasonal_operation_status", "temporary_closure", "public_notice"])
                relevance["seasonal_operation_status"] = 0.85
            if has_ticket:
                supports.append("ticket_price")
                relevance["ticket_price"] = 0.75
            elif has_about:
                relevance["ticket_price"] = 0.2
            if has_hours:
                supports.append("opening_hours")
                relevance["opening_hours"] = 0.8

        elif source_class == SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL:
            supports.append("destination_background")
            relevance["destination_background"] = 0.85
            if has_ticket:
                supports.append("ticket_price")
                relevance["ticket_price"] = 0.92
            if has_hours:
                supports.append("opening_hours")
                relevance["opening_hours"] = 0.9
            if has_notice:
                supports.append("temporary_closure")
                relevance["temporary_closure"] = 0.85

        elif source_class == SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE:
            supports.append("destination_background")
            relevance["destination_background"] = 0.7
            if has_ticket:
                supports.append("ticket_price")
                relevance["ticket_price"] = 0.65
            if has_hours:
                supports.append("opening_hours")
                relevance["opening_hours"] = 0.75

        elif source_class in {SOURCE_CLASS_OTA_PLATFORM, SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE}:
            if has_ticket:
                supports.append("ticket_price")
                relevance["ticket_price"] = 0.55
            relevance["review_signal"] = 0.5

        elif source_class == SOURCE_CLASS_REVIEW_PLATFORM:
            supports.append("review_signal")
            relevance["review_signal"] = 0.7
            if has_ticket:
                relevance["ticket_price"] = 0.35

        elif source_class == SOURCE_CLASS_MAP_PROVIDER_CANDIDATE:
            if has_hours:
                supports.append("opening_hours")
                relevance["opening_hours"] = 0.55
            relevance["entity_resolution"] = 0.7

        return supports, relevance

    @staticmethod
    def _guess_organization(title: str | None, domain: str, blob: str) -> str | None:
        if title and any(h in title for h in ("管委会", "文旅局", "旅游开发", "管理处")):
            return title[:80]
        if _GOV_DOMAIN_RE.search(domain):
            return domain
        m = re.search(r"([\u4e00-\u9fff]{2,20}(?:旅游开发|管委会|管理处|有限公司))", blob)
        if m:
            return m.group(1)
        return None
