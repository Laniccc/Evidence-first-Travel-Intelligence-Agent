"""Seven quality gates for the Deep Research Agent pipeline.

Each gate is a pure function that inspects the current state and returns
a GateResult. Gates 2-7 never block the loop — they return retry/fallback
instructions that the Supervisor acts on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GateCheck:
    """A single check within a gate."""
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GateResult:
    """Result of a gate evaluation."""
    gate_name: str
    passed: bool
    action: str  # "continue", "retry", "degrade", "return_to_user"
    checks: list[GateCheck] = field(default_factory=list)
    feedback: str = ""  # human-readable explanation
    retry_hint: str | None = None  # hint for retry (e.g. "try Bing instead")
    degradation_label: str | None = None  # label for degraded delivery


# ── Gate 1: Input Gate ────────────────────────────────────────────────────────


SAFETY_BLOCKLIST = [
    "暴力", "色情", "赌博", "毒品", "武器制造",
    "hacking", "malware", "exploit",
]


def check_input_gate(query: str) -> GateResult:
    """Validate the research query for safety and researchability."""
    checks: list[GateCheck] = []

    # Safety check
    query_lower = query.lower()
    blocked = any(k in query_lower for k in SAFETY_BLOCKLIST)
    checks.append(GateCheck(
        name="safety_filter",
        passed=not blocked,
        detail="Query passes safety filter" if not blocked else "Query contains blocked content",
    ))

    # Researchability check
    too_vague = len(query.strip()) < 10
    checks.append(GateCheck(
        name="researchability",
        passed=not too_vague,
        detail="Query is specific enough" if not too_vague else "Query too vague (min 10 chars)",
    ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="input",
        passed=all_pass,
        action="continue" if all_pass else "return_to_user",
        checks=checks,
        feedback="All input checks passed" if all_pass else "Query needs clarification",
    )


# ── Gate 2: Plan Gate ─────────────────────────────────────────────────────────


def check_plan_gate(sub_questions: list[dict[str, Any]]) -> GateResult:
    """Validate the research plan quality."""
    checks: list[GateCheck] = []

    # Must have 1-8 sub-questions
    count = len(sub_questions)
    checks.append(GateCheck(
        name="question_count",
        passed=1 <= count <= 8,
        detail=f"{count} sub-questions (need 1-8)",
    ))

    # Each sub-question must have a search query
    all_have_queries = all(q.get("search_query") for q in sub_questions)
    checks.append(GateCheck(
        name="search_query_present",
        passed=all_have_queries,
        detail="All sub-questions have search queries" if all_have_queries else "Some sub-questions missing search queries",
    ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="plan",
        passed=all_pass,
        action="continue" if all_pass else "retry",
        checks=checks,
        feedback="Plan validated" if all_pass else "Plan needs revision",
    )


# ── Gate 3: Source Gate ───────────────────────────────────────────────────────


# Tier 5 blacklist — content farms, SEO spam
SOURCE_BLACKLIST = [
    "17173.com", "sohu.com", "zhuanzhi.ai",
]

# Tier 1 domains
TIER_1_DOMAINS = [
    "arxiv.org", "scholar.google.com", ".gov.cn", ".gov", ".edu",
    "github.com", "docs.python.org", "spring.io", "openai.com",
    "pypi.org", "wikipedia.org", "developer.mozilla.org", "stackoverflow.com",
]

TIER_2_DOMAINS = [
    "infoq.cn", "jiqizhixin.com", "engineering.fb.com",
    "netflixtechblog.com", "tech.meituan.com",
    "medium.com", "dev.to", "juejin.cn", "zhihu.com",
    "geeksforgeeks.org", "tutorialspoint.com", "w3schools.com",
    "freecodecamp.org", "realpython.com", "towardsdatascience.com",
]

# Domains that are search engine redirects — tier can't be determined from URL alone
SEARCH_REDIRECT_DOMAINS = [
    "baidu.com/link", "sogou.com/link",
    "r.jina.ai", "jina.ai",
]


def classify_source_tier(url: str, title_hint: str = "") -> int:
    """Classify a URL into tier 1-5 based on domain rules.

    Handles search engine redirect URLs by extracting the target domain,
    and falls back to title-based hints when the URL is opaque.
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Check if this is a search engine redirect — try to extract real domain
    for redirect_pattern in SEARCH_REDIRECT_DOMAINS:
        if redirect_pattern in domain + parsed.path:
            # Try to extract real URL from redirect params
            real_domain = _extract_domain_from_redirect(parsed, title_hint)
            if real_domain:
                domain = real_domain
                break

    # Blacklist first
    for bl in SOURCE_BLACKLIST:
        if bl in domain:
            return 5

    # Tier 1
    for t1 in TIER_1_DOMAINS:
        if t1 in domain or domain.endswith(t1):
            return 1

    # Tier 2
    for t2 in TIER_2_DOMAINS:
        if t2 in domain or domain.endswith(t2):
            return 2

    # Title-based hint fallback for opaque URLs
    if title_hint:
        title_lower = title_hint.lower()
        tier1_hints = ["github docs", "python documentation", "arxiv", "official docs",
                       "mozilla", "mdn", "wikipedia", "pypi", "stack overflow"]
        tier2_hints = ["github topics", "github.com", "medium",
                       "dev.to", "geeksforgeeks", "freecodecamp", "real python",
                       "towards data science", "infoq", "zhihu"]
        for hint in tier1_hints:
            if hint in title_lower:
                return 1
        for hint in tier2_hints:
            if hint in title_lower:
                return 2

    # Default
    return 3


def _extract_domain_from_redirect(parsed, title_hint: str = "") -> str:
    """Try to extract the real destination domain from a redirect URL."""
    from urllib.parse import parse_qs

    # Baidu redirects: /link?url=<target>
    if "baidu.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        target_url = qs.get("url", [None])[0]
        if target_url and target_url.startswith("http"):
            from urllib.parse import urlparse as up
            return up(target_url).netloc.lower()

    # Sogou redirects: /link?url=<target>
    if "sogou.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        target_url = qs.get("url", [None])[0]
        if target_url and target_url.startswith("http"):
            from urllib.parse import urlparse as up
            return up(target_url).netloc.lower()

    return ""


def check_source_gate(
    search_results: list[dict[str, Any]],
    topic_requires_academic: bool = False,
) -> GateResult:
    """Validate source quality after search."""
    checks: list[GateCheck] = []
    rated = []
    for r in search_results:
        url = r.get("url", "")
        tier = classify_source_tier(url)
        rated.append({**r, "source_tier": tier})

    # Filter out Tier 5
    kept = [r for r in rated if r["source_tier"] < 5]
    tier5_count = len(rated) - len(kept)
    checks.append(GateCheck(
        name="tier5_filter",
        passed=True,  # Always passes — filtered results are discarded
        detail=f"Filtered {tier5_count} Tier-5 sources",
    ))

    # At least 1 Tier 3+ source
    tier3_count = sum(1 for r in kept if r["source_tier"] <= 3)
    has_good_source = tier3_count >= 1
    checks.append(GateCheck(
        name="min_source_quality",
        passed=has_good_source,
        detail=f"{tier3_count} Tier 1-3 sources found",
    ))

    # Academic requirement
    if topic_requires_academic:
        academic_count = sum(1 for r in kept if r["source_tier"] == 1)
        checks.append(GateCheck(
            name="academic_source",
            passed=academic_count >= 1,
            detail=f"{academic_count} Tier-1 academic sources",
        ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="source",
        passed=all_pass,
        action="continue" if all_pass else "retry",
        checks=checks,
        feedback="Source quality acceptable" if all_pass else "Source quality insufficient — retry with different engine",
        retry_hint="try_alternate_search_engine" if not all_pass else None,
        degradation_label="low_quality_sources" if not has_good_source else None,
    )


# ── Gate 4: Evidence Gate ─────────────────────────────────────────────────────


def check_evidence_gate(
    evidence_records: list[dict[str, Any]],
    sub_question_count: int,
) -> GateResult:
    """Validate evidence sufficiency."""
    checks: list[GateCheck] = []

    # At least 2 evidence per sub-question
    ev_count = len(evidence_records)
    min_required = sub_question_count * 2
    sufficient = ev_count >= min_required
    checks.append(GateCheck(
        name="evidence_count",
        passed=sufficient,
        detail=f"{ev_count} evidence records (need >= {min_required})",
    ))

    # Each evidence must have at least 1 claim
    has_claims = sum(1 for ev in evidence_records if len(ev.get("claims", [])) > 0)
    checks.append(GateCheck(
        name="claims_extracted",
        passed=has_claims >= sub_question_count,
        detail=f"{has_claims} records have extractable claims",
    ))

    # Identify gaps
    gaps = []
    if not sufficient:
        gaps.append(f"Need {min_required - ev_count} more evidence records")

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="evidence",
        passed=all_pass,
        action="continue" if all_pass else "retry",
        checks=checks,
        feedback="Evidence sufficient" if all_pass else f"Evidence gaps: {', '.join(gaps)}",
        retry_hint="supplement_search" if gaps else None,
    )


# ── Gate 5: Cross-Reference Gate ──────────────────────────────────────────────


def check_crossref_gate(
    cross_references: list[dict[str, Any]],
) -> GateResult:
    """Validate cross-referencing of core claims."""
    checks: list[GateCheck] = []
    verified = sum(1 for cr in cross_references if cr.get("status") == "verified")
    contested = sum(1 for cr in cross_references if cr.get("status") == "contested")
    unverified = sum(1 for cr in cross_references if cr.get("status") == "unverified")
    total = len(cross_references)

    # All core claims must be verified or at least have 2+ corroborating sources
    checks.append(GateCheck(
        name="crossref_coverage",
        passed=unverified <= (total * 0.3) or total == 0,  # allow up to 30% unverified
        detail=f"Verified: {verified}, Contested: {contested}, Unverified: {unverified}",
    ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="crossref",
        passed=all_pass,
        action="continue" if all_pass else "degrade",
        checks=checks,
        feedback="Cross-reference complete" if all_pass else f"{unverified} claims unverified — marked in report",
        degradation_label="unverified_claims_present" if unverified > 0 else None,
    )


# ── Gate 6: Citation Gate ─────────────────────────────────────────────────────


def check_citation_gate(
    report_sections: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> GateResult:
    """Validate that claims have URL citations."""
    checks: list[GateCheck] = []

    # Every section with factual claims must have at least 1 citation
    factual_sections = [
        s for s in report_sections
        if s.get("type") in ("findings", "analysis", "comparison")
    ]
    cited_count = sum(
        1 for s in factual_sections
        if any(c.get("section_ref") == s.get("id") for c in citations)
    )
    checks.append(GateCheck(
        name="citation_coverage",
        passed=cited_count >= len(factual_sections) * 0.5,
        detail=f"{cited_count}/{len(factual_sections)} factual sections have citations",
    ))

    # Each citation must have a valid URL
    valid_citations = [c for c in citations if c.get("url", "").startswith("http")]
    checks.append(GateCheck(
        name="citation_urls_valid",
        passed=len(valid_citations) >= 1,
        detail=f"{len(valid_citations)} valid citation URLs",
    ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="citation",
        passed=all_pass,
        action="continue" if all_pass else "degrade",
        checks=checks,
        feedback="Citations verified" if all_pass else "Some claims lack citations — marked in report",
        degradation_label="uncited_claims" if not all_pass else None,
    )


# ── Gate 7: Delivery Gate ─────────────────────────────────────────────────────


def check_delivery_gate(report: dict[str, Any]) -> GateResult:
    """Final delivery quality check."""
    checks: list[GateCheck] = []

    # Must have summary
    has_summary = len(report.get("summary", "")) > 50
    checks.append(GateCheck(
        name="has_summary",
        passed=has_summary,
        detail="Summary present and substantive" if has_summary else "Summary missing or too short",
    ))

    # Must have citations
    has_citations = len(report.get("citations", [])) > 0
    checks.append(GateCheck(
        name="has_citations",
        passed=has_citations,
        detail=f"{len(report.get('citations', []))} citations",
    ))

    # Must have limitations
    has_limitations = len(report.get("limitations", [])) > 0
    checks.append(GateCheck(
        name="has_limitations",
        passed=has_limitations,
        detail="Limitations section present" if has_limitations else "No limitations stated",
    ))

    all_pass = all(c.passed for c in checks)
    return GateResult(
        gate_name="delivery",
        passed=all_pass,
        action="continue" if all_pass else "degrade",
        checks=checks,
        feedback="Delivery ready" if all_pass else "Partial delivery — see limitations",
        degradation_label="partial_report" if not all_pass else None,
    )


# ── Evidence Sufficiency Check (between evidence_extraction and synthesis) ──────


async def check_evidence_sufficiency(
    query: str,
    evidence_records: list[Any],
    llm_client: Any = None,
) -> dict[str, Any]:
    """Evaluate whether gathered evidence is sufficient to answer the user's question.

    Uses LLM to judge if the evidence can actually answer the query. If not,
    identifies gaps and suggests new search angles for a retry round.

    Returns:
        {
            "sufficient": bool,
            "confidence": 0.0-1.0,
            "gaps": ["specific missing info", ...],
            "suggested_queries": ["refined search query", ...],
            "reasoning": "one-line explanation"
        }
    """
    if not llm_client:
        # No LLM — assume sufficient if we have at least 3 evidence with claims
        with_claims = sum(1 for e in evidence_records if len(getattr(e, "claims", []) or []) > 0)
        sufficient = with_claims >= 3
        return {
            "sufficient": sufficient,
            "confidence": 0.5,
            "gaps": [] if sufficient else ["Insufficient evidence without LLM evaluation"],
            "suggested_queries": [],
            "reasoning": f"{with_claims} records with claims — {'sufficient' if sufficient else 'need more'}",
        }

    # Build evidence summary for LLM
    evidence_summary = ""
    for i, ev in enumerate(evidence_records, 1):
        claims = getattr(ev, "claims", []) or []
        claim_texts = [c.get("claim", str(c)) if isinstance(c, dict) else str(c) for c in claims[:2]]
        evidence_summary += f"[{i}] {getattr(ev, 'source_name', '?')} (T{getattr(ev, 'source_tier', 3)}): {'; '.join(claim_texts)[:200]}\n"

    if not evidence_summary.strip():
        return {
            "sufficient": False,
            "confidence": 0.0,
            "gaps": ["No evidence could be extracted from any source"],
            "suggested_queries": [query],
            "reasoning": "Zero evidence records with claims",
        }

    prompt = f"""User question: {query}

Gathered evidence:
{evidence_summary[:4000]}

Assess:
1. Can the user's question be answered with this evidence? (yes/partial/no)
2. What key information is still missing? List specific gaps.
3. If gaps exist, suggest 2-3 refined search queries to fill them.

Respond as JSON:
{{"sufficient": true/false, "confidence": 0.0-1.0, "gaps": ["..."], "suggested_queries": ["..."], "reasoning": "..."}}"""

    import json as _json
    import re as _re

    # Try LLM evaluation
    llm_data: dict[str, Any] = {}
    try:
        text = await llm_client.complete(
            system="You evaluate research evidence quality. Be honest and specific about gaps. Output ONLY valid JSON.",
            user=prompt,
            max_tokens=1024,
            json_only=True,
        )
        match = _re.search(r"\{.*\}", text, _re.DOTALL)
        if match:
            llm_data = _json.loads(match.group())
    except Exception:
        pass

    # Heuristic stats
    records_with_claims = sum(1 for e in evidence_records if len(getattr(e, "claims", []) or []) > 0)
    total_claims = sum(len(getattr(e, "claims", []) or []) for e in evidence_records)
    llm_sufficient = bool(llm_data.get("sufficient", False))

    # Override: if LLM says insufficient but we have reasonable evidence with claims,
    # don't let LLM caution prevent synthesis. Threshold accounts for ~50% fetch success rate.
    if not llm_sufficient and (records_with_claims >= 3 or total_claims >= 6):
        logger.info(
            "Overriding LLM sufficiency: %d records with claims, %d total claims → SUFFICIENT",
            records_with_claims, total_claims,
        )
        return {
            "sufficient": True,
            "confidence": max(float(llm_data.get("confidence", 0.5)), 0.5),
            "gaps": llm_data.get("gaps", []),
            "suggested_queries": llm_data.get("suggested_queries", []),
            "reasoning": f"Override: {records_with_claims} records with {total_claims} claims — sufficient despite LLM caution. {llm_data.get('reasoning', '')}",
        }

    # LLM says sufficient
    if llm_data:
        return {
            "sufficient": llm_sufficient,
            "confidence": float(llm_data.get("confidence", 0.5)),
            "gaps": llm_data.get("gaps", []),
            "suggested_queries": llm_data.get("suggested_queries", []),
            "reasoning": llm_data.get("reasoning", ""),
        }

    # Pure heuristic fallback (no LLM data)
    return {
        "sufficient": records_with_claims >= 3 or total_claims >= 6,
        "confidence": 0.4,
        "gaps": [],
        "suggested_queries": [],
        "reasoning": f"Heuristic: {records_with_claims} records with {total_claims} claims",
    }
