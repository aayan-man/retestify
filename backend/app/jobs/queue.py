from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.knowledge_base.schema import utcnow

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "succeeded", "failed"]
ACTIVE_STATUSES: tuple[JobStatus, ...] = ("queued", "running")


class JobConflictError(Exception):
    """Another job is already queued or running for this project."""


class Job(BaseModel):
    """A long-running pipeline call tracked outside the request that started
    it, so the client can poll instead of holding a connection open."""

    id: str
    project_id: str
    kind: str
    status: JobStatus = "queued"
    processed: int = 0
    total: int | None = None
    error: str | None = None
    # Small summary of what the job did (counts, not payloads) — the results
    # themselves are read back from the knowledge base as usual.
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobQueue:
    """An in-process background runner for the pipeline's slow calls.

    Applying a project is one LLM round trip per recommendation and can run
    for minutes; doing that inside the request meant a browser or proxy
    timeout discarded the whole run. Jobs run on a thread pool instead
    (the pipeline is blocking I/O, so it must stay off the event loop) and
    the client polls for progress.

    Only one job at a time is allowed per project, because the knowledge
    base is a set of JSON files that concurrent runs would interleave
    writes into.

    State is in memory and therefore single-process: a restart loses job
    history, and running more than one worker process would give each its
    own queue. Results are always persisted to the knowledge base by the
    pipeline itself, so a lost job record never means lost work.
    """

    def __init__(self, max_workers: int | None = None, history: int = 200):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers or settings.job_max_workers, thread_name_prefix="job"
        )
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._history = history

    def submit(self, project_id: str, kind: str, run: Callable[[Callable[[int, int], None]], dict[str, Any]]) -> Job:
        """Queue `run` for execution. It is handed a `progress(processed,
        total)` callback and returns a small result summary.

        Raises JobConflictError if this project already has an active job.
        """
        job = Job(id=f"job_{uuid.uuid4().hex[:10]}", project_id=project_id, kind=kind)
        with self._lock:
            active = self._active_for_project_locked(project_id)
            if active is not None:
                raise JobConflictError(
                    f"project {project_id} already has a {active.kind} job in progress ({active.id})"
                )
            self._jobs[job.id] = job
            self._trim_locked()

        self._executor.submit(self._run, job.id, run)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_for_project(self, project_id: str) -> list[Job]:
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def active_for_project(self, project_id: str) -> Job | None:
        with self._lock:
            return self._active_for_project_locked(project_id)

    # -- internals ---------------------------------------------------------

    def _active_for_project_locked(self, project_id: str) -> Job | None:
        for job in self._jobs.values():
            if job.project_id == project_id and job.status in ACTIVE_STATUSES:
                return job
        return None

    def _trim_locked(self) -> None:
        """Drop the oldest finished jobs once history grows past the cap, so
        a long-lived server doesn't accumulate them forever."""
        while len(self._jobs) > self._history:
            for job_id, job in self._jobs.items():
                if job.status not in ACTIVE_STATUSES:
                    del self._jobs[job_id]
                    break
            else:
                return  # everything still active; nothing safe to drop

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._jobs[job_id] = job.model_copy(update=fields)

    def _run(self, job_id: str, run: Callable[[Callable[[int, int], None]], dict[str, Any]]) -> None:
        self._update(job_id, status="running", started_at=utcnow())

        def progress(processed: int, total: int) -> None:
            self._update(job_id, processed=processed, total=total)

        try:
            result = run(progress)
        except Exception as e:
            logger.exception("Job %s failed", job_id)
            self._update(job_id, status="failed", error=str(e), finished_at=utcnow())
            return
        self._update(job_id, status="succeeded", result=result, finished_at=utcnow())


queue = JobQueue()
