import pytest
from app.orchestration.publication_observation import publication_snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("result,status,index", [
    ({"status": "rejected"}, "rejected", "not_applicable"),
    ({"status": "pending"}, "pending_review", "not_applicable"),
    ({"status": "active", "job_id": "j"}, "published", "pending"),
])
async def test_publication_is_not_index_success(result, status, index):
    async def lookup(_):
        return {"status": "pending"}
    summary, sync = await publication_snapshot({"results": [result]}, job_reader=lookup)
    assert summary.status == status and sync.status == index


@pytest.mark.asyncio
async def test_index_success_requires_receipt_and_unknown_does_not_invent_success():
    async def indexed(_):
        return {"status": "succeeded", "generation_id": "g"}
    summary, sync = await publication_snapshot({"results": [{"status": "active", "job_id": "j"}]}, job_reader=indexed)
    assert sync.status == "indexed" and sync.indexed_count == 1
    async def broken(_):
        raise RuntimeError("private-key")
    summary, sync = await publication_snapshot({"results": [{"status": "active", "job_id": "j"}]}, job_reader=broken)
    assert summary.status == "published" and sync.status == "unknown"
    assert "private" not in summary.model_dump_json() + sync.model_dump_json()


@pytest.mark.asyncio
async def test_disabled_failure_and_mixed_candidates():
    disabled, _ = await publication_snapshot({"failure_code": "storage_not_permitted"})
    assert disabled.status == "disabled"
    failed, _ = await publication_snapshot({"failure_code": "promotion_failed"})
    assert failed.status == "failed"
    unknown, _ = await publication_snapshot({"failure_code": "promotion_persistence_unknown"})
    assert unknown.status == "unknown"
    mixed, _ = await publication_snapshot({"results": [{"status": "active"}, {"status": "rejected"}]})
    assert mixed.status == "partial" and mixed.published_count == mixed.rejected_count == 1
