import pytest

from app.composition.answer_claim import AnswerClaim
from app.evidence.citation_checker import CitationChecker
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.citation_guard import CitationGuardHandler


def hard_claim(evidence_ids, *, conflict_disclosed=False):
    return AnswerClaim(
        claim_id="claim-1",
        text="每日 09:00 开放",
        claim_type="opening_hours",
        hard_fact=True,
        evidence_ids=evidence_ids,
        attraction_id="forbidden-city",
        subtask_id="sub-1",
        conflict_disclosed=conflict_disclosed,
    )


def evidence(**updates):
    value = {
        "evidence_id": "e-1",
        "source_url": "https://example.test/hours",
        "document_version_id": "v-1",
        "version_status": "active",
        "content_hash": "hash-1",
        "active_content_hash": "hash-1",
        "content": "每日 09:00 开放",
    }
    value.update(updates)
    return value


@pytest.mark.parametrize(
    "bad_evidence",
    [
        evidence(version_status="expired"),
        evidence(source_url=None),
        evidence(active_content_hash="different"),
    ],
)
def test_invalid_evidence_cannot_support_hard_fact(bad_evidence):
    report = CitationChecker().check(
        claims=[hard_claim(["e-1"])], evidence_index={"e-1": bad_evidence}
    )

    assert report.decisions[0].status == "unsupported_removed"
    assert report.unsupported_hard_fact_count == 1


def test_missing_evidence_id_is_removed():
    report = CitationChecker().check(
        claims=[hard_claim(["missing"])], evidence_index={}
    )

    assert report.decisions[0].reason == "missing_evidence_id"


def test_unreported_conflict_is_removed_but_disclosed_conflict_is_supported():
    index = {
        "e-1": evidence(),
        "e-2": evidence(
            evidence_id="e-2",
            content="每日 08:30 开放",
            content_hash="hash-2",
            active_content_hash="hash-2",
        ),
    }

    hidden = CitationChecker().check(
        claims=[hard_claim(["e-1", "e-2"])], evidence_index=index
    )
    disclosed = CitationChecker().check(
        claims=[hard_claim(["e-1", "e-2"], conflict_disclosed=True)],
        evidence_index=index,
    )

    assert hidden.decisions[0].reason == "unreported_conflict"
    assert disclosed.decisions[0].status == "supported"


def test_soft_advice_does_not_require_hard_citation():
    claim = AnswerClaim(
        claim_id="soft-1",
        text="建议预留充足时间",
        claim_type="advice",
        hard_fact=False,
    )

    report = CitationChecker().check(claims=[claim], evidence_index={})

    assert report.decisions[0].status == "soft_claim_allowed"
    assert report.safe_failure is False


@pytest.mark.asyncio
async def test_guard_safe_fails_when_all_hard_facts_are_removed():
    state = StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
        artifacts={
            "compose": {
                "answer_claims": [hard_claim(["missing"]).model_dump(mode="json")],
                "evidence_index": {},
            }
        },
    )

    result = await CitationGuardHandler().run(state)

    assert result.next_state is AgentState.SAFE_FAILURE
    assert result.output["citation_report"]["safe_failure"] is True
