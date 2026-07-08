"""Unit tests for pipeline helper functions — URL resolution, redirect detection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_core.phases.evidence_acquisition import _is_redirect_url
from app.agent_core.phases.evidence_extraction import (
    _is_search_redirect,
    _extract_real_url,
)


# ═══ Redirect URL detection ═══

@pytest.mark.parametrize("url,expected", [
    ("http://www.baidu.com/link?url=abc123", True),
    ("https://www.baidu.com/link?url=xyz", True),
    ("http://www.sogou.com/link?url=abc", True),
    ("https://github.com/trending", False),
    ("https://docs.python.org/3/", False),
    ("https://blog.csdn.net/article/123", False),
    ("https://realpython.com/langgraph", False),
    ("https://www.google.com/search?q=test", False),  # Google is not in redirect list
    ("", False),
])
def test_is_search_redirect(url, expected):
    assert _is_search_redirect(url) == expected


def test_is_search_redirect_consistency():
    """_is_redirect_url in evidence_acquisition should be consistent with _is_search_redirect."""
    test_urls = [
        "http://www.baidu.com/link?url=abc",
        "http://www.sogou.com/link?url=abc",
        "https://github.com/trending",
    ]
    for url in test_urls:
        assert _is_redirect_url(url) == _is_search_redirect(url), f"Mismatch for {url}"


# ═══ Real URL extraction from content ═══

def test_extract_real_url_canonical():
    html = '<html><head><link rel="canonical" href="https://realpython.com/langgraph-python/"></head></html>'
    result = _extract_real_url(html)
    assert result == "https://realpython.com/langgraph-python/"


def test_extract_real_url_og_url():
    html = '<meta property="og:url" content="https://example.com/article">'
    result = _extract_real_url(html)
    assert result == "https://example.com/article"


def test_extract_real_url_none():
    assert _extract_real_url(None) is None
    assert _extract_real_url("") is None


def test_extract_real_url_text_content():
    """When content is extracted text (not HTML), look for source URLs."""
    text = "Article from CSDN blog. 原文链接：https://blog.csdn.net/user/article/123456"
    result = _extract_real_url(text)
    assert result == "https://blog.csdn.net/user/article/123456"


def test_extract_real_url_ignores_baidu_redirect():
    """Should not match baidu redirect URLs as 'real' URLs."""
    text = "原文链接：http://www.baidu.com/link?url=abc123"
    result = _extract_real_url(text)
    # Should NOT return the baidu link as a real URL
    assert result is None or "baidu.com/link" not in (result or "")


# ═══ Evidence record tier classification ═══

from app.agent_core.state.models import EvidenceRecord


def test_evidence_record_default_tier():
    ev = EvidenceRecord(
        evidence_id="ev_test",
        run_id="run_test",
        source_name="Test Source",
        source_url="https://example.com",
        source_type="web",
    )
    assert ev.source_tier == 3  # Default


def test_evidence_record_custom_tier():
    ev = EvidenceRecord(
        evidence_id="ev_test",
        run_id="run_test",
        source_name="GitHub",
        source_url="https://github.com/trending",
        source_type="web",
        source_tier=1,
    )
    assert ev.source_tier == 1


def test_evidence_record_claims():
    ev = EvidenceRecord(
        evidence_id="ev_test",
        run_id="run_test",
        source_name="Test",
        source_url="https://example.com",
        source_type="web",
        claims=[{"claim": "Fact 1", "type": "fact"}, {"claim": "Fact 2", "type": "analysis"}],
    )
    assert len(ev.claims) == 2
