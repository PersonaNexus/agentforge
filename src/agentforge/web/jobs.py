"""Job store with in-memory SSE streaming and optional DB persistence."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """A tracked async job (forge, batch, import, extract)."""

    id: str
    status: str = "pending"  # pending | running | done | error
    events: queue.Queue = field(default_factory=queue.Queue)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    _on_complete: Callable[[Job], None] | None = field(default=None, repr=False)

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Push an SSE event onto the queue."""
        self.events.put(json.dumps({"event": event, **(data or {})}))

    def emit_stage(self, stage: str, message: str) -> None:
        self.emit("stage", {"stage": stage, "message": message})

    def emit_done(self, result: dict[str, Any]) -> None:
        self.result = result
        self.status = "done"
        self.emit("done", result)
        if self._on_complete:
            try:
                self._on_complete(self)
            except Exception:
                logger.exception("Failed to persist job completion")

    def emit_error(self, message: str) -> None:
        self.error = message
        self.status = "error"
        self.emit("error", {"message": message})
        if self._on_complete:
            try:
                self._on_complete(self)
            except Exception:
                logger.exception("Failed to persist job error")


class JobStore:
    """Thread-safe job store with in-memory SSE + optional DB persistence.

    In-memory dict is a hot cache for active/recent jobs.
    DB (when configured) provides durable persistence that survives restarts.
    """

    _TTL_SECONDS = 1800  # 30 minutes

    def __init__(self, session_factory: Any | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._session_factory = session_factory

    def create(
        self,
        job_type: str = "forge",
        source_filename: str | None = None,
        mode: str | None = None,
        model: str | None = None,
        output_format: str | None = None,
    ) -> Job:
        """Create a new job in memory and DB."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id)

        if self._session_factory:
            job._on_complete = self._persist_completion

        with self._lock:
            self._jobs[job_id] = job

        # Persist to DB
        if self._session_factory:
            try:
                from agentforge.web.db.repository import JobRepository

                with self._session_factory() as session:
                    repo = JobRepository(session)
                    repo.create(
                        job_id=job_id,
                        job_type=job_type,
                        source_filename=source_filename,
                        mode=mode,
                        model=model,
                        output_format=output_format,
                    )
            except Exception:
                logger.exception("Failed to persist new job to DB")

        return job

    def get(self, job_id: str) -> Job | None:
        """Get a job — checks in-memory first, then falls back to DB."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return job

        # Fall through to DB for completed jobs (e.g., after restart)
        if self._session_factory:
            return self._load_from_db(job_id)

        return None

    def persist_result(self, job: Job) -> None:
        """Explicitly persist current job result to DB (e.g., after refine)."""
        if not self._session_factory:
            return
        try:
            from agentforge.web.db.repository import JobRepository

            with self._session_factory() as session:
                repo = JobRepository(session)
                repo.update_result(
                    job.id,
                    status=job.status,
                    result=job.result,
                    error=job.error,
                )
        except Exception:
            logger.exception("Failed to persist job result")

    def cleanup(self) -> int:
        """Remove expired jobs from in-memory cache. DB rows are permanent."""
        cutoff = time.time() - self._TTL_SECONDS
        removed = 0
        with self._lock:
            expired = [k for k, v in self._jobs.items() if v.created_at < cutoff]
            for k in expired:
                del self._jobs[k]
                removed += 1
        return removed

    def recover_stale_jobs(self) -> int:
        """Mark any DB jobs stuck in 'running' as error (startup recovery)."""
        if not self._session_factory:
            return 0
        try:
            from agentforge.web.db.repository import JobRepository

            with self._session_factory() as session:
                repo = JobRepository(session)
                return repo.mark_stale_running_as_error()
        except Exception:
            logger.exception("Failed to recover stale jobs")
            return 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist_completion(self, job: Job) -> None:
        """Callback invoked by Job.emit_done/emit_error to persist to DB."""
        if not self._session_factory:
            return
        from agentforge.web.db.repository import JobRepository

        with self._session_factory() as session:
            repo = JobRepository(session)
            repo.update_result(
                job.id,
                status=job.status,
                result=job.result,
                error=job.error,
            )

    def _load_from_db(self, job_id: str) -> Job | None:
        """Load a completed job from DB into an in-memory Job (no SSE queue)."""
        from agentforge.web.db.repository import JobRepository

        try:
            with self._session_factory() as session:
                repo = JobRepository(session)
                row = repo.get(job_id)
                if not row:
                    return None

                result = None
                if row.result_json:
                    result = json.loads(row.result_json)

                job = Job(
                    id=row.id,
                    status=row.status,
                    result=result,
                    error=row.error,
                    created_at=row.created_at.timestamp() if row.created_at else time.time(),
                )

                # Cache it in memory
                with self._lock:
                    self._jobs[job_id] = job

                return job
        except Exception:
            logger.exception("Failed to load job from DB")
            return None
