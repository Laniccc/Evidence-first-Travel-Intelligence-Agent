import json

import pytest

from app.contracts.baidu import BaiduPoiBinding
from app.integrations.mcp.baidu_gap_tool import BaiduGapTool
from app.integrations.mcp.stdio_session import ToolCallReceipt
from app.integrations.mcp.tool_catalog import MCPBoundaryError, ToolCatalog
from app.orchestration.states.live_gap_fill import LiveGapFillHandler
from app.orchestration.state_contracts import AgentState
from tests.states.test_live_gap_fill import context
from tests.fakes.failing_retrievers import plan


TOOLS = [
    {"name": "map_search_places", "inputSchema": {"type": "object", "properties": {
        "query": {"type": "string"}, "region": {"type": "string"}}, "required": ["query"]}},
    {"name": "map_place_details", "inputSchema": {"type": "object", "properties": {
        "uid": {"type": "string"}, "scope": {"type": "string"}}, "required": ["uid"]}},
]
POI = {"name": "颐和园", "uid": "uid2", "city": "北京市", "address": "新建宫门路19号",
       "detail_info": {"detail_url": "https://api.map.baidu.com/place/detail?uid=uid2&output=html",
                       "shop_hours": "06:30-18:00"}}


class Session:
    def __init__(self, *, poi=None, ambiguous=False, failures=()):
        self.catalog = ToolCatalog(TOOLS)
        self.poi = POI if poi is None else poi
        self.ambiguous = ambiguous
        self.failures = list(failures)
        self.calls = []
        self.restarts = 0

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if self.failures:
            failure = self.failures.pop(0)
            if failure:
                raise MCPBoundaryError(failure)
        if name == "map_search_places":
            payload = {"results": [self.poi]}
            if self.ambiguous:
                payload["results"].append({**self.poi, "uid": "other"})
        else:
            payload = self.poi
        return ToolCallReceipt(name, "call-" + str(len(self.calls)), self.catalog.hashes[name],
                               {"content": [{"type": "text", "text": json.dumps(payload)}]})

    async def restart(self):
        self.restarts += 1


def binding(attraction_id):
    return BaiduPoiBinding(attraction_id=attraction_id, name="颐和园", city="北京")


def comparison():
    ctx = context()
    left = plan(subtask_id="left", task_type="comparison")
    right = plan(subtask_id="right", attraction_id="summer-palace", task_type="comparison")
    ctx.artifacts["retrieval_plan"]["retrieval_plans"] = [p.model_dump(mode="json") for p in (left, right)]
    ctx.artifacts["evidence_evaluate"]["coverage_report"]["items"] = [
        {"claim_type": "left:opening_hours", "covered": True},
        {"claim_type": "right:opening_hours", "covered": False},
    ]
    return ctx


@pytest.mark.asyncio
async def test_comparison_fills_second_attraction_and_counts_actual_tools():
    session = Session()
    ctx = comparison()
    result = await LiveGapFillHandler(tool=BaiduGapTool(session, binding_resolver=binding)).run(ctx)
    assert result.next_state is AgentState.EVIDENCE_EVALUATE
    assert result.output["gap_task"]["subtask_id"] == "right"
    assert [c[0] for c in session.calls] == ["map_search_places", "map_place_details"]
    assert ctx.budget.used_tool_calls == result.output["tool_call_attempt_count"] == 2
    evidence = result.output["transient_evidence"][0]
    assert evidence["attraction_id"] == "summer-palace"
    assert evidence["subtask_id"] == "right" and evidence["content"] == "06:30-18:00"
    assert len(evidence["content_hash"]) == 64 and evidence["provenance_ref"]
    assert result.output["mcp_envelopes"][0]["sanitized_fields"]
    assert not result.output["active_index_updated"]


@pytest.mark.asyncio
@pytest.mark.parametrize("poi,ambiguous,code", [
    (POI, True, "ambiguous_entity"),
    ({**POI, "city": "上海市"}, False, "entity_not_found"),
    ({**POI, "detail_info": {"shop_hours": "08:30"}}, False, "source_url_missing"),
    ({**POI, "detail_info": {"detail_url": "https://api.map.baidu.com/place/detail?uid=uid2&ak=secret",
                           "shop_hours": "08:30"}}, False, "invalid_source_url"),
    ({**POI, "detail_info": {"detail_url": POI["detail_info"]["detail_url"]}}, False, "required_field_missing"),
])
async def test_unbound_or_incomplete_provider_data_is_not_delivered(poi, ambiguous, code):
    session = Session(poi=poi, ambiguous=ambiguous)
    result = await LiveGapFillHandler(tool=BaiduGapTool(session, binding_resolver=binding)).run(comparison())
    assert result.output["transient_evidence"] == []
    assert result.output["failure_code"] == code
    assert result.status == "recovered" and result.recovery.strategy == "gap_unavailable"
    assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_rate_limit_retry_has_per_tool_limit_and_four_call_ceiling():
    session = Session(failures=["rate_limit", None, "rate_limit", None])
    ctx = comparison()
    result = await LiveGapFillHandler(tool=BaiduGapTool(session, binding_resolver=binding)).run(ctx)
    assert len(session.calls) == ctx.budget.used_tool_calls == 4
    assert result.output["transient_evidence"]
    assert [a["attempt"] for a in result.output["attempts"]] == [1, 2, 1, 2]
    assert result.recovery.strategy == "gap_retried"


@pytest.mark.asyncio
async def test_unsupported_fact_and_historical_query_do_not_call_current_map_snapshot():
    for updates, code in [({"fact_types": ["accessibility"]}, "unsupported_fact"),
                          ({"require_explicit_temporal_coverage": True}, "temporal_scope_unsupported")]:
        ctx = context()
        ctx.artifacts.pop("evidence_evaluate")
        ctx.artifacts["retrieval_plan"]["retrieval_plans"][0].update(updates)
        session = Session()
        result = await LiveGapFillHandler(tool=BaiduGapTool(session, binding_resolver=binding)).run(ctx)
        assert session.calls == []
        assert ctx.budget.used_tool_calls == 0
        assert result.output["failure_code"] == code


@pytest.mark.asyncio
async def test_known_uid_skips_search_and_deadline_retry_reinitializes_once():
    session = Session(failures=["tool_timeout", None])
    tool = BaiduGapTool(session, binding_resolver=lambda identity: binding(identity).model_copy(
        update={"provider_uid": "uid2"}))
    ctx = comparison()
    result = await LiveGapFillHandler(tool=tool).run(ctx)
    assert [name for name, _ in session.calls] == ["map_place_details"] * 2
    assert session.restarts == 1 and result.output["transient_evidence"]


@pytest.mark.asyncio
async def test_budget_exhaustion_preserves_existing_evidence_and_stops_before_next_call():
    from app.governance.tool_budget import RunBudget
    ctx = comparison()
    ctx.budget = RunBudget(max_tool_calls=1)
    ctx.artifacts["hybrid_retrieve"] = {"retrieval_reports": [{"sentinel": "left retained"}]}
    session = Session()
    result = await LiveGapFillHandler(tool=BaiduGapTool(session, binding_resolver=binding)).run(ctx)
    assert len(session.calls) == ctx.budget.used_tool_calls == 1
    assert result.output["failure_code"] == "tool_budget_exhausted"
    assert ctx.artifacts["hybrid_retrieve"]["retrieval_reports"] == [{"sentinel": "left retained"}]


@pytest.mark.asyncio
async def test_actual_stdio_protocol_to_normalized_evidence():
    from tests.integrations.test_stdio_session import session
    async with session("baidu") as client:
        ctx = comparison()
        result = await LiveGapFillHandler(tool=BaiduGapTool(client, binding_resolver=binding)).run(ctx)
        assert result.output["tool_call_attempt_count"] == 2
        assert result.output["transient_evidence"][0]["content"] == "06:30-18:00"
        assert result.output["mcp_envelopes"][0]["provider_entity_id"] == "uid2"


@pytest.mark.asyncio
async def test_total_gap_deadline_is_audited_and_cancellation_is_not_retried():
    import asyncio
    cancelled = asyncio.Event()

    class Slow(Session):
        async def call_tool(self, name, args):
            self.calls.append((name, args))
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    client = Slow()
    ctx = comparison()
    result = await LiveGapFillHandler(tool=BaiduGapTool(
        client, binding_resolver=binding, deadline_seconds=0.02)).run(ctx)
    assert cancelled.is_set()
    assert result.output["failure_code"] == "gap_deadline_exceeded"
    assert result.output["attempts"][0]["failure_code"] == "tool_cancelled"
    assert ctx.budget.used_tool_calls == 1 and len(client.calls) == 1
