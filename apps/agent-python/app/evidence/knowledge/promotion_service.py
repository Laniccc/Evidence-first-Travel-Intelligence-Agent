"""One transaction for validation decision, immutable version, publish and outbox."""
from datetime import UTC, datetime
import json
from uuid import uuid4


class PromotionService:
    def __init__(self, repository, validator):
        self.repository, self.validator = repository, validator

    def promote(self, raw, envelopes, *, name, run_id, query_id, trace_id):
        decision = self.validator.validate(raw, envelopes)
        document = None if decision.outcome == "rejected" else self.validator.document(
            decision, raw, envelopes, name=name)
        with self.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version_id, job_id, status = None, None, "rejected"
            if document:
                ingested = self.repository._ingest(db, document)
                version_id = ingested.version_id
                status = ingested.status.value
                if decision.outcome == "auto_publish" and status in {"pending", "active"}:
                    self.repository._publish(db, version_id)
                    status = "active"
                    job_id = self._enqueue(db, version_id, run_id, query_id, trace_id)
                # Terminal historical versions are never reactivated on repeat input.
            db.execute("""INSERT INTO promotion_decision VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("decision-" + str(uuid4()), decision.candidate_id, run_id, query_id, trace_id,
                 decision.outcome, json.dumps(decision.reason_codes), json.dumps(decision.evidence_refs),
                 decision.policy_version, version_id, datetime.now(UTC).isoformat()))
        return {"decision": decision.model_dump(mode="json"), "version_id": version_id,
                "job_id": job_id, "status": status}

    @staticmethod
    def _enqueue(db, version_id, run_id, query_id, trace_id):
        db.execute("""INSERT INTO index_sync_job(job_id,dedupe_key,version_id,status,run_id,query_id,trace_id)
                    VALUES (?,?,?,'pending',?,?,?) ON CONFLICT(dedupe_key) DO NOTHING""",
                   ("job-" + str(uuid4()), "publish:" + version_id, version_id, run_id, query_id, trace_id))
        return db.execute("SELECT job_id FROM index_sync_job WHERE dedupe_key=?", ("publish:" + version_id,)).fetchone()[0]
