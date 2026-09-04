from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.evidence.citation_checker import CitationChecker
from tests.states.test_citation_guard import hard_claim, evidence


@pytest.mark.parametrize("updates,reason", [
    ({"content": "门票六十元"}, "content_not_supported"),
    ({"attraction_id": "other"}, "attraction_mismatch"),
    ({"fact_type": "ticket_price"}, "fact_type_mismatch"),
    ({"subtask_id": "other"}, "subtask_mismatch"),
    ({"document_version_id": None}, "missing_version_id"),
    ({"valid_to": "2020-01-01T00:00:00Z"}, "evidence_expired"),
])
def test_real_citation_id_does_not_imply_support(updates, reason):
    row = evidence(attraction_id="forbidden-city", fact_type="opening_hours", subtask_id="sub-1", **updates) if not any(k in updates for k in ("attraction_id", "fact_type", "subtask_id")) else evidence(**{
        "attraction_id": "forbidden-city", "fact_type": "opening_hours", "subtask_id": "sub-1", **updates})
    report = CitationChecker.check(claims=[hard_claim(["e-1"])], evidence_index={"e-1": row})
    assert report.decisions[0].reason == reason and report.safe_failure


def test_price_claim_disguised_as_advice_is_rejected():
    claim = hard_claim([]).model_copy(update={"text": "建议放心游览，门票免费", "hard_fact": False, "claim_type": "advice"})
    result = CitationChecker.check(claims=[claim], evidence_index={})
    assert result.safe_failure and result.decisions[0].status == "unsupported_removed"


def test_transient_hash_must_match_actual_content():
    row = evidence(transient=True, version_status="transient", retrieved_at=datetime.now(UTC),
        valid_to=datetime.now(UTC) + timedelta(hours=1), provenance_ref="call", content_hash="fake", active_content_hash="fake")
    result = CitationChecker.check(claims=[hard_claim(["e-1"])], evidence_index={"e-1": row})
    assert result.decisions[0].reason == "transient_hash_mismatch"


def test_unapproved_fact_cannot_be_added_after_evidence_evaluate():
    result = CitationChecker.check(claims=[hard_claim(["e-1"])], evidence_index={"e-1": evidence()}, approved_decisions=[])
    assert result.safe_failure
