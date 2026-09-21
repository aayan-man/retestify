import threading
import time

import pytest

from app.jobs.queue import JobConflictError, JobQueue


def _wait_for(predicate, timeout_s: float = 5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within %ss" % timeout_s)


def test_job_runs_in_the_background_and_records_its_result():
    queue = JobQueue()
    job = queue.submit("proj", "apply", lambda progress: {"applied": 3})

    assert job.status == "queued"
    _wait_for(lambda: queue.get(job.id).status == "succeeded")

    finished = queue.get(job.id)
    assert finished.result == {"applied": 3}
    assert finished.started_at is not None and finished.finished_at is not None
    assert finished.error is None


def test_progress_is_visible_while_the_job_is_still_running():
    queue = JobQueue()
    release = threading.Event()

    def run(progress):
        progress(2, 5)
        release.wait(timeout=5)
        return {}

    job = queue.submit("proj", "apply", run)
    try:
        _wait_for(lambda: queue.get(job.id).processed == 2)
        mid = queue.get(job.id)
        assert mid.status == "running"
        assert (mid.processed, mid.total) == (2, 5)
    finally:
        release.set()


def test_a_failing_job_records_the_error_instead_of_raising():
    queue = JobQueue()
    job = queue.submit("proj", "apply", lambda progress: (_ for _ in ()).throw(RuntimeError("boom")))

    _wait_for(lambda: queue.get(job.id).status == "failed")
    assert "boom" in queue.get(job.id).error


def test_only_one_job_per_project_may_be_active():
    """Concurrent runs would interleave writes into the same knowledge-base
    files, so a second job for the same project is refused."""
    queue = JobQueue()
    release = threading.Event()
    job = queue.submit("proj", "apply", lambda progress: release.wait(timeout=5) and {})

    try:
        _wait_for(lambda: queue.get(job.id).status == "running")
        with pytest.raises(JobConflictError, match="already has a"):
            queue.submit("proj", "classify", lambda progress: {})

        # A different project is unaffected.
        other = queue.submit("other-proj", "classify", lambda progress: {})
        _wait_for(lambda: queue.get(other.id).status == "succeeded")
    finally:
        release.set()

    # Once the first job finishes, the project accepts work again.
    _wait_for(lambda: queue.get(job.id).status == "succeeded")
    queue.submit("proj", "classify", lambda progress: {})


def test_jobs_are_listed_per_project_newest_first():
    queue = JobQueue()
    first = queue.submit("proj", "classify", lambda progress: {})
    _wait_for(lambda: queue.get(first.id).status == "succeeded")
    second = queue.submit("proj", "apply", lambda progress: {})
    _wait_for(lambda: queue.get(second.id).status == "succeeded")
    queue.submit("elsewhere", "apply", lambda progress: {})

    listed = queue.list_for_project("proj")

    assert [j.id for j in listed] == [second.id, first.id]


def test_finished_jobs_are_trimmed_but_active_ones_are_kept():
    queue = JobQueue(history=2)
    release = threading.Event()
    active = queue.submit("busy", "apply", lambda progress: release.wait(timeout=5) and {})
    try:
        _wait_for(lambda: queue.get(active.id).status == "running")
        for i in range(5):
            done = queue.submit("p%d" % i, "classify", lambda progress: {})
            _wait_for(lambda: queue.get(done.id) is None or queue.get(done.id).status == "succeeded")

        assert queue.get(active.id) is not None, "a running job must never be trimmed"
    finally:
        release.set()


def test_unknown_job_id_returns_none():
    assert JobQueue().get("job_nope") is None
