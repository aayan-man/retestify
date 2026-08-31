from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.repo_manager.workspace import Workspace


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
