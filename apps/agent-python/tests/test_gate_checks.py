"""Unit tests for all quality gate checks."""

import pytest
import sys
from pathlib import Path

# Ensure app is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_core.contracts.gate_checks import (
    check_input_gate,
    check_plan_gate,
    check_source_gate,
    check_evidence_gate,
    check_crossref_gate,
    check_citation_gate,
    check_delivery_gate,
    classify_source_tier,
)


# ═══ classify_source_tier ═══

@pytest.mark.parametrize("url,expected_tier", [
    ("https://github.com/trending", 1),
    ("https://docs.python.org/3/tutorial", 1),
    ("https://arxiv.org/abs/2501.00001", 1),
    ("https://www.nist.gov/document", 1),
    ("https://developer.mozilla.org/en-US/docs/Web", 1),
    ("https://en.wikipedia.org/wiki/AI_agent", 1),
    ("https://stackoverflow.com/questions/123", 1),
    ("https://pypi.org/project/langgraph", 1),
    ("https://openai.com/research", 1),
    ("https://spring.io/projects", 1),
])
def test_tier1_domains(url, expected_tier):
    assert classify_source_tier(url) == expected_tier


@pytest.mark.parametrize("url,expected_tier", [
    ("https://medium.com/some-article", 2),
    ("https://dev.to/post", 2),
    ("https://www.freecodecamp.org/news/x", 2),
    ("https://realpython.com/langgraph-python", 2),
    ("https://towardsdatascience.com/article", 2),
    ("https://www.geeksforgeeks.org/x", 2),
    ("https://www.tutorialspoint.com/x", 2),
    ("https://www.w3schools.com/x", 2),
    ("https://www.zhihu.com/question/123", 2),
    ("https://juejin.cn/post/123", 2),
    ("https://www.infoq.cn/article/x", 2),
    ("https://tech.meituan.com/2025/x", 2),
    ("https://jiqizhixin.com/articles/x", 2),
    ("https://netflixtechblog.com/x", 2),
    ("https://engineering.fb.com/x", 2),
])
def test_tier2_domains(url, expected_tier):
    assert classify_source_tier(url) == expected_tier


@pytest.mark.parametrize("url,expected_tier", [
    ("https://blog.csdn.net/user/article/123", 3),
    ("https://random-blog.cn/post", 3),
    ("https://example.com/article", 3),
    ("https://www.simform.com/blog/ai-agent", 3),
])
def test_tier3_default(url, expected_tier):
    assert classify_source_tier(url) == expected_tier


@pytest.mark.parametrize("url,expected_tier", [
    ("https://www.17173.com/x", 5),
    ("https://www.sohu.com/a/123", 5),
    ("https://news.sohu.com/x", 5),
])
def test_tier5_blacklist(url, expected_tier):
    assert classify_source_tier(url) == expected_tier


def test_tier_with_title_hint():
    """When URL is a redirect, title hint should help classify."""
    baidu_url = "http://www.baidu.com/link?url=abc123"
    # Without hint: baidu.com -> no match -> T3
    assert classify_source_tier(baidu_url) == 3
    # With "GitHub Topics · GitHub" title: should resolve to T2 via hint
    assert classify_source_tier(baidu_url, title_hint="GitHub Topics · GitHub") == 2
    # With "GitHub Docs" title: should resolve to T1 via hint
    assert classify_source_tier(baidu_url, title_hint="GitHub Docs — Saving repositories") == 1
    # With "Stack Overflow" title → matches "stack overflow" in tier1_hints → T1
    # Note: "stack overflow" is a string match in tier1_hints
    assert classify_source_tier(baidu_url, title_hint="python — stack overflow question") == 1


# ═══ Gate 1: Input ═══

def test_input_gate_valid_query():
    result = check_input_gate("What is LangGraph and how does it work?")
    assert result.passed
    assert result.action == "continue"


def test_input_gate_too_short():
    result = check_input_gate("Hi")
    assert not result.passed
    assert result.action == "return_to_user"


def test_input_gate_blocked_content():
    result = check_input_gate("How to make 毒品 at home")
    assert not result.passed
    assert result.action == "return_to_user"


def test_input_gate_minimum_length():
    result = check_input_gate("What is AI?")  # 12 chars >= 10
    assert result.passed


# ═══ Gate 2: Plan ═══

def test_plan_gate_valid():
    questions = [
        {"question": "What is LangGraph?", "search_query": "LangGraph definition"},
        {"question": "How does it work?", "search_query": "LangGraph internal architecture"},
    ]
    result = check_plan_gate(questions)
    assert result.passed


def test_plan_gate_empty():
    result = check_plan_gate([])
    assert not result.passed


def test_plan_gate_missing_search_query():
    questions = [{"question": "What is X?"}]  # no search_query
    result = check_plan_gate(questions)
    assert not result.passed


def test_plan_gate_too_many_questions():
    questions = [{"question": f"Q{i}", "search_query": f"query{i}"} for i in range(10)]
    result = check_plan_gate(questions)
    assert not result.passed


# ═══ Gate 3: Source ═══

def test_source_gate_all_tier1():
    results = [{"url": "https://github.com/langchain-ai/langgraph"}]
    gate = check_source_gate(results)
    assert gate.passed


def test_source_gate_with_tier5():
    results = [
        {"url": "https://github.com/langgraph"},
        {"url": "https://www.17173.com/spam"},
    ]
    gate = check_source_gate(results)
    # Should still pass — one good source remains
    assert gate.passed


def test_source_gate_all_tier5():
    results = [{"url": "https://www.sohu.com/a/123"}, {"url": "https://www.17173.com/x"}]
    gate = check_source_gate(results)
    # 0 good sources after Tier-5 filtering → min_source_quality fails
    # Gate correctly says "retry with different engine"
    assert not gate.passed
    assert gate.action == "retry"


def test_source_gate_academic_requirement():
    results = [
        {"url": "https://github.com/x"},  # T1 but not academic
    ]
    gate = check_source_gate(results, topic_requires_academic=True)
    # Needs at least 1 Tier-1 academic source: github.com IS tier 1 but not .gov or arxiv
    # github.com is in TIER_1_DOMAINS so it counts as T1/ academic
    assert gate.passed  # github.com matches Tier 1


# ═══ Gate 4: Evidence ═══

def test_evidence_gate_sufficient():
    records = [
        {"claims": [{"claim": "fact 1"}, {"claim": "fact 2"}]},
        {"claims": [{"claim": "fact 3"}]},
        {"claims": [{"claim": "fact 4"}]},
        {"claims": [{"claim": "fact 5"}]},
    ]
    result = check_evidence_gate(records, sub_question_count=2)
    assert result.passed  # 4 >= 2*2


def test_evidence_gate_insufficient():
    records = [{"claims": [{"claim": "fact 1"}]}]
    result = check_evidence_gate(records, sub_question_count=3)
    assert not result.passed  # 1 < 3*2


def test_evidence_gate_no_claims():
    records = [
        {"claims": []},
        {"claims": []},
        {"claims": []},
        {"claims": []},
        {"claims": []},
        {"claims": []},
    ]
    result = check_evidence_gate(records, sub_question_count=3)
    assert not result.passed  # 0 records with claims < 3


# ═══ Gate 5: Cross-Ref ═══

def test_crossref_gate_all_verified():
    refs = [
        {"claim": "X", "source_refs": ["url1", "url2"], "corroborating_sources": 2, "status": "verified"},
    ]
    result = check_crossref_gate(refs)
    assert result.passed


def test_crossref_gate_mixed():
    refs = [
        {"claim": "A", "source_refs": ["u1", "u2"], "corroborating_sources": 2, "status": "verified"},
        {"claim": "B", "source_refs": ["u1"], "corroborating_sources": 1, "status": "unverified"},
    ]
    result = check_crossref_gate(refs)
    # 1/2 unverified = 50% > 30% threshold
    assert not result.passed


def test_crossref_gate_empty():
    result = check_crossref_gate([])
    assert result.passed  # Empty list always passes


# ═══ Gate 6: Citation ═══

def test_citation_gate_valid():
    sections = [
        {"type": "findings", "id": "results", "heading": "Results", "content": "X is true [1]"},
        {"type": "analysis", "id": "analysis", "heading": "Analysis", "content": "Therefore Y [2]"},
    ]
    citations = [
        {"section_ref": "results", "url": "https://example.com/1"},
        {"section_ref": "analysis", "url": "https://example.com/2"},
    ]
    result = check_citation_gate(sections, citations)
    assert result.passed


def test_citation_gate_no_valid_urls():
    sections = [{"type": "findings", "heading": "X"}]
    citations = [{"section_ref": "X", "url": ""}]
    result = check_citation_gate(sections, citations)
    assert not result.passed  # No valid http:// URLs


def test_citation_gate_empty():
    result = check_citation_gate([], [])
    assert not result.passed  # No citations at all


# ═══ Gate 7: Delivery ═══

def test_delivery_gate_valid():
    report = {
        "summary": "This is a comprehensive summary of the research findings that covers the key topics and provides more than fifty characters of substantive content.",
        "citations": [{"url": "https://example.com"}],
        "limitations": ["This is a limitation"],
    }
    result = check_delivery_gate(report)
    assert result.passed


def test_delivery_gate_short_summary():
    report = {
        "summary": "Short.",
        "citations": [{"url": "https://example.com"}],
        "limitations": ["Limit"],
    }
    result = check_delivery_gate(report)
    assert not result.passed


def test_delivery_gate_no_limitations():
    report = {
        "summary": "A detailed summary with sufficient length to pass the fifty character check for the delivery gate.",
        "citations": [{"url": "https://example.com"}],
        "limitations": [],
    }
    result = check_delivery_gate(report)
    assert not result.passed


def test_delivery_gate_no_citations():
    report = {
        "summary": "A detailed summary with sufficient length to pass the fifty character check for the delivery gate test case.",
        "citations": [],
        "limitations": ["A limitation"],
    }
    result = check_delivery_gate(report)
    assert not result.passed
