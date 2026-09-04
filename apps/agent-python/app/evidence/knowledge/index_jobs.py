"""Single-instance durable coordinator; bounded retries and fenced SQLite leases."""
from datetime import UTC, datetime, timedelta


class IndexJobs:
    def __init__(self, repository, synchronizer, *, clock=None):
        self.repository, self.synchronizer = repository, synchronizer
        self.clock = clock or (lambda: datetime.now(UTC))

    def get(self, job_id):
        with self.repository._connect() as db:
            row = db.execute("SELECT * FROM index_sync_job WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def _claim(self):
        now = self.clock()
        with self.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE index_sync_job SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END,
                lease_until=NULL, last_failure_code='lease_expired'
                WHERE status='running' AND lease_until<=?""", (now.isoformat(),))
            if db.execute("SELECT 1 FROM index_sync_job WHERE status='running'").fetchone():
                return None
            row = db.execute("""SELECT * FROM index_sync_job WHERE status='pending' AND attempts<3
                AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY rowid LIMIT 1""", (now.isoformat(),)).fetchone()
            if row is None:
                return None
            db.execute("""UPDATE index_sync_job SET status='running', attempts=attempts+1, lease_until=?
                WHERE job_id=? AND status='pending'""", ((now + timedelta(minutes=5)).isoformat(), row["job_id"]))
            return dict(db.execute("SELECT * FROM index_sync_job WHERE job_id=?", (row["job_id"],)).fetchone())

    def run_pending(self, *, limit=10):
        if not 1 <= limit <= 100:
            raise ValueError("job_limit_out_of_bounds")
        results = []
        for _ in range(limit):
            job = self._claim()
            if job is None:
                break
            failure, generation_id = None, None
            try:
                result = self.synchronizer.rebuild(corpus_version=self.repository.compute_corpus_version())
                generation_id = result.generation_id
                failure = result.cleanup_failure_code
                status = "succeeded"
            except Exception as exc:
                generation_id = getattr(exc, "generation_id", None)
                # Never retain a provider exception string or response in the outbox.
                failure = "index_sync_failed"
                if generation_id:
                    failure = self.repository.get_index_generation(generation_id).failure_code or failure
                status = "failed" if job["attempts"] >= 3 else "pending"
            with self.repository._connect() as db:
                db.execute("""UPDATE index_sync_job SET status=?, lease_until=NULL, next_attempt_at=?,
                    last_failure_code=?, generation_id=? WHERE job_id=? AND status='running' AND attempts=?""",
                    (status, (self.clock() + timedelta(seconds=10 * job["attempts"])).isoformat() if status == "pending" else None,
                     failure, generation_id, job["job_id"], job["attempts"]))
            results.append(self.get(job["job_id"]))
        return results
