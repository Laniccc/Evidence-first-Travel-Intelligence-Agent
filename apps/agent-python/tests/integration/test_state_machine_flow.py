from dataclasses import dataclass

import pytest

from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.state_machine import TravelAgentStateMachine
from tests.fakes.failing_retrievers import chunk, report


@dataclass(frozen=True)
class AttractionMatch:
    attraction_id: str
    name: str
    city: str = "北京"
    country: str = "中国"


CATALOG = [
    AttractionMatch("forbidden-city", "故宫博物院"),
    AttractionMatch("summer-palace", "颐和园"),
]


def matcher(text: str):
    aliases = {"故宫博物院": ("故宫博物院", "故宫"), "颐和园": ("颐和园",)}
    return [
        item
        for item in CATALOG
        if any(alias in text for alias in aliases[item.name])
    ]


def resolver(name: str):
    for item in CATALOG:
        if name in {item.name, "故宫"} and item.attraction_id == "forbidden-city":
            return item.attraction_id
        if name == item.name:
            return item.attraction_id
    return None


class CompleteRetriever:
    def retrieve(self, retrieval_plan):
        hits = [
            chunk(
                f"{retrieval_plan.attraction_ids[0]}-{fact_type.value}",
                f"{retrieval_plan.attraction_ids[0]} 的 {fact_type.value} 有官方资料支持",
                fact_type=fact_type.value,
                attraction_id=retrieval_plan.attraction_ids[0],
            )
            for fact_type in retrieval_plan.fact_types
        ]
        return report(retrieval_plan, hits=hits)


class LexicalFallbackRetriever(CompleteRetriever):
    def retrieve(self, retrieval_plan):
        result = super().retrieve(retrieval_plan)
        return result.model_copy(
            update={
                "degradation": "lexical_only",
                "dense_attempt": result.dense_attempt.model_copy(
                    update={"status": "failed", "result_count": 0, "failure_code": "timeout"}
                ),
            }
        )


class EmptyRetriever:
    def retrieve(self, retrieval_plan):
        return report(retrieval_plan, hits=[], degradation="no_results")


def machine(retriever, *, run_store=None):
    return TravelAgentStateMachine(
        retriever=retriever,
        attraction_resolver=resolver,
        attraction_matcher=matcher,
        run_store=run_store,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_state"),
    [
        ("故宫几点开放", "fact_query"),
        ("故宫适合带老人吗", "suitability"),
        ("比较故宫和颐和园", "comparison"),
    ],
)
async def test_supported_tasks_share_one_grounded_state_chain(query, expected_state):
    response = await machine(CompleteRetriever()).run(query, session_id="session-1")

    audit = response.orchestration_summary["state_audit"]
    started = [item["state"] for item in audit if item["event_type"] == "phase_started"]
    assert expected_state in started
    assert started[-3:] == ["evidence_evaluate", "compose", "citation_guard"]
    assert response.orchestration_summary["terminal_state"] == "deliver"
    assert response.answer_claims
    assert response.citation_report["citation_precision"] == 1.0


@pytest.mark.asyncio
async def test_dense_timeout_is_audited_and_lexical_evidence_still_delivers():
    response = await machine(LexicalFallbackRetriever()).run("故宫几点开放")

    retrieval = response.retrieval_reports[0]
    assert retrieval["degradation"] == "lexical_only"
    assert retrieval["dense_attempt"]["failure_code"] == "timeout"
    recovered = [
        item
        for item in response.orchestration_summary["state_audit"]
        if item["event_type"] == "phase_recovered"
    ]
    assert recovered[0]["recovery"]["strategy"] == "lexical_only"
    assert response.answer_claims


@pytest.mark.asyncio
async def test_two_empty_channels_attempt_one_gap_task_then_abstain():
    response = await machine(EmptyRetriever()).run("故宫几点开放")

    started = [
        item["state"]
        for item in response.orchestration_summary["state_audit"]
        if item["event_type"] == "phase_started"
    ]
    assert started.count("live_gap_fill") == 1
    assert response.orchestration_summary["terminal_state"] == "safe_failure"
    assert response.answer_claims == []


@pytest.mark.asyncio
async def test_run_ledger_contains_full_artifacts_for_inspect_and_replay(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    response = await machine(CompleteRetriever(), run_store=store).run(
        "故宫几点开放", session_id="session-1", trace_id="trace-1"
    )

    inspection = store.inspect(response.query_id)
    assert inspection.run.current_state == "deliver"
    assert inspection.run.session_id == "session-1"
    assert inspection.answer_claims
    assert inspection.metrics["citation_precision"] == 1.0
    assert store.latest_state_output(
        inspection.run.run_id, "hybrid_retrieve"
    )["retrieval_reports"]


@pytest.mark.asyncio
async def test_multi_turn_reference_uses_session_context():
    response = await machine(CompleteRetriever()).run(
        "它几点开放",
        session_id="session-1",
        user_context={
            "conversation_context": {
                "last_places": ["故宫博物院"],
                "last_city": "北京",
                "last_country": "中国",
            }
        },
    )

    assert response.orchestration_summary["terminal_state"] == "deliver"
    assert response.answer_claims
