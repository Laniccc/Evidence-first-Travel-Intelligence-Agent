"""Read-only, allowlisted publication snapshot; never expose provider payloads."""
import asyncio
from app.contracts.response import PromotionSummary, IndexSyncStatus


async def publication_snapshot(artifact, *, job_reader=None):
    if not artifact:
        return PromotionSummary(status="not_attempted"), IndexSyncStatus(status="not_applicable")
    rows = artifact.get("results", [])
    published = [r for r in rows if r.get("status") == "active"]
    pending = sum(r.get("status") == "pending" for r in rows)
    rejected = sum(r.get("status") == "rejected" for r in rows)
    failure = artifact.get("failure_code")
    if failure == "storage_not_permitted":
        status = "disabled"
    elif failure == "promotion_persistence_unknown":
        status = "unknown"
    elif failure:
        status = "partial" if rows else "failed"
    elif len(published) == len(rows) and rows:
        status = "published"
    elif pending == len(rows) and rows:
        status = "pending_review"
    elif rejected == len(rows) and rows:
        status = "rejected"
    else:
        status = "partial" if rows else "not_attempted"
    summary = PromotionSummary(status=status, candidate_count=len(rows), published_count=len(published),
                               pending_count=pending, rejected_count=rejected)
    counts = {"pending": 0, "indexed": 0, "failed": 0, "unknown": 0}
    for row in published:
        state = "unknown"
        if job_reader and row.get("job_id"):
            try:
                async with asyncio.timeout(0.5):
                    job = await job_reader(row["job_id"])
                if job and job.get("status") in {"pending", "running"}:
                    state = "pending"
                elif job and job.get("status") == "failed":
                    state = "failed"
                elif job and job.get("status") == "succeeded" and job.get("generation_id"):
                    state = "indexed"
            except Exception:
                pass  # Observation failure must not invalidate already guarded Evidence.
        counts[state] += 1
    index_state = next((s for s in ("unknown", "failed", "pending", "indexed") if counts[s]), "not_applicable")
    if failure == "promotion_persistence_unknown":
        index_state = "unknown"
    return summary, IndexSyncStatus(status=index_state, pending_count=counts["pending"],
        indexed_count=counts["indexed"], failed_count=counts["failed"])
