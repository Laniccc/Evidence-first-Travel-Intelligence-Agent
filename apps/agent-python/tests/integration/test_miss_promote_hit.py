import pytest

from evals.closure_runtime import run_dense_closure


@pytest.mark.asyncio
async def test_miss_promote_durable_sync_then_dense_only_hit_and_effect_free_replay(tmp_path):
    result = await run_dense_closure(tmp_path)
    assert result["first_tool_calls"] == 2
    assert result["promotion_status"] == "active"
    assert result["sync_recovery"] == 1
    assert result["promotion_idempotency"] == 1
    assert result["miss_promote_dense_hit"] == 1
    assert result["second_tool_calls"] == 0
    assert result["unsupported_emitted"] == 0
    assert result["replay_external_calls"] == 0
    assert result["replay_write_side_effects"] == 0
    assert result["replay_consistent"]
