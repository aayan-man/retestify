from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from pydantic import BaseModel

from app.repo_manager.workspace import Workspace


def overall_status(totals: Mapping[str, int]) -> str:
    """Collapse per-outcome totals into a run status.

    A run that produced no test results at all is "error", never "passed".
    Zero failures is only good news when something actually ran; an empty
    report usually means the suite never started (container failure,
    collection error, missing report file), and calling that a pass is a
    false green — the worst way for a test tool to be wrong.
    """
    if totals["total"] == 0:
        return "error"
    return "passed" if totals["failed"] == 0 and totals["errors"] == 0 else "failed"


class TestOutcome(BaseModel):
    name: str
    status: str  # passed | failed | error | skipped
    duration_ms: int
    message: str | None = None


class RunResult(BaseModel):
    run_id: str
    status: str  # passed | failed | error
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: int
    outcomes: list[TestOutcome] = []
    coverage_percent: float | None = None
    stdout: str = ""
    stderr: str = ""


class TestRunner(ABC):
    """Executes a target repo's test suite. Every implementation must run
    target-repo code (and any AI-generated code) inside an isolated sandbox
    — see test_runner.sandbox_exec — never directly on the host."""

    language: str

    @abstractmethod
    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 120) -> RunResult: ...
