import json
from pathlib import Path

import pytest

from app.orchestrator.state_machine import TravelAgentStateMachine


@pytest.mark.asyncio
async def test_conflict_detection_structure():
    sm = TravelAgentStateMachine()
    resp = await sm.run("北京故宫明天值得去吗？")
    assert isinstance(resp.conflicts, list)


@pytest.mark.asyncio
async def test_unsupported_region():
    sm = TravelAgentStateMachine()
    resp = await sm.run("巴黎埃菲尔铁塔值得去吗？")
    assert "日本" in resp.answer or "中国" in resp.answer or "韩国" in resp.answer
    assert resp.confidence <= 0.5
