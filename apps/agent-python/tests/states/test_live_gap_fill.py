import pytest

from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.live_gap_fill import LiveGapFillHandler
from tests.fakes.failing_retrievers import plan


def context():
    retrieval_plan = plan()
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
        artifacts={
            "retrieval_plan": {
                "retrieval_plans": [retrieval_plan.model_dump(mode="json")]
            },
            "evidence_evaluate": {
                "coverage_report": {
                    "items": [
                        {
                            "claim_type": "opening_hours",
                            "covered": False,
                            "missing_reason": "no_active_evidence",
                        }
                    ]
                }
            },
        },
    )


class RateLimitThenSuccess:
    def __init__(self):
        self.calls = 0

    async def fetch(self, task, *, attempt):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("429 rate limit")
        return {
            "evidence_id": "live-1",
            "attraction_id": "forbidden-city",
            "fact_type": "opening_hours",
            "content": "故宫今日八点三十分开放",
            "source_name": "故宫官网",
            "source_url": "https://www.dpm.org.cn/visit/hours",
        }


@pytest.mark.asyncio
async def test_gap_fill_allows_429_then_success_with_two_attempt_cap():
    state = context()
    result = await LiveGapFillHandler(tool=RateLimitThenSuccess()).run(state)

    assert result.next_state is AgentState.EVIDENCE_EVALUATE
    assert [item["status"] for item in result.output["attempts"]] == ["failed", "success"]
    assert result.output["transient_evidence"][0]["transient"] is True
    assert result.output["logical_gap_task_count"] == 1
    assert state.budget.used_tool_calls == 1


class MalformedPayload:
    async def fetch(self, task, *, attempt):
        return {"unexpected": True}


@pytest.mark.asyncio
async def test_malformed_payload_is_audited_and_stops_after_two_attempts():
    result = await LiveGapFillHandler(tool=MalformedPayload()).run(context())

    assert result.next_state is AgentState.EVIDENCE_EVALUATE
    assert len(result.output["attempts"]) == 2
    assert {item["failure_code"] for item in result.output["attempts"]} == {
        "malformed_payload"
    }
    assert result.output["transient_evidence"] == []
