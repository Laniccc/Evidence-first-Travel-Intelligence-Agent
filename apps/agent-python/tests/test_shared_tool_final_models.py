import pytest

from app.evidence.evidence_model import Claim, Evidence
from app.evidence.official_source import OfficialSourceDiscoveryResult
from app.evidence.ticket_info import TicketSnapshot
from app.integrations.storage.tool_cache import get_tool_cache
from app.understanding.travel_task import TravelTask
from tools import hybrid_tool
from tools.adapters import mcp_tool_adapter
from tools.mcp.adapters import nearby_poi_claims
from tools.official_source.official_source_discovery_tool import OfficialSourceDiscoveryTool
from tools.official_source import official_source_discovery_tool
from tools.ticketing import ticket_snapshot_store
from tools.tool_router import ToolRouter


def test_shared_tool_modules_use_final_model_types():
    assert mcp_tool_adapter.Claim is Claim
    assert mcp_tool_adapter.Evidence is Evidence
    assert official_source_discovery_tool.OfficialSourceDiscoveryResult is OfficialSourceDiscoveryResult
    assert ticket_snapshot_store.TicketSnapshot is TicketSnapshot


def test_shared_tool_behavior_dependencies_use_final_owners():
    cache = get_tool_cache()
    cache.clear()
    try:
        cache.set("shared-tool-test", ["cached"], place="Beijing Zoo")
        assert cache.get("shared-tool-test", place="Beijing Zoo") == ["cached"]
    finally:
        cache.clear()

    assert hybrid_tool.get_tool_cache is get_tool_cache
    assert nearby_poi_claims.normalize_nearby_need("nearby_dining") == "nearby_food"

    plan = ToolRouter().route([], TravelTask(country="CN", city="Beijing"))
    assert "official" in plan.selected_tools
    assert any("SourceSelectionPolicy" in line for line in plan.routing_explanation)


@pytest.mark.asyncio
async def test_official_discovery_uses_final_ticket_relevance_policy():
    result = await OfficialSourceDiscoveryTool().run(
        place_name="Beijing Zoo",
        country="CN",
        claim_type="ticket_price",
        search_results=[
            {
                "url": "https://example.com/beijing-zoo-ticket",
                "title": "Beijing Zoo official ticket price",
                "snippet": "ticket price",
            }
        ],
        probe_top_n=0,
    )

    assert result
