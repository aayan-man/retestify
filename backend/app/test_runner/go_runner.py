from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.config import settings
from app.repo_manager.workspace import Workspace

from .base import RunResult, TestOutcome, TestRunner, overall_status
from .sandbox_exec import ensure_runner_image, run_in_container, runner_image_tag

# Go ships its test runner in the toolchain, so nothing needs installing --
# but the module cache and build cache must live somewhere writable, and
# GOFLAGS/GOPROXY are set so the offline run never attempts a fetch.
GO_RUNNER_DOCKERFILE = """FROM {base}
ENV GOPATH=/go GOCACHE=/go/.cache GOFLAGS=-mod=mod GOPROXY=off
RUN mkdir -p /go/.cache
"""


class GoRunner(TestRunner):
    """Runs `go test` and parses its JSON event stream.

    Go emits one JSON object per event rather than a report file, so the
    stream is written to a file in the workspace and parsed afterwards, the
    same way the other runners consume a report.
    """

    language = "go"

    def __init__(self, image: str | None = None):
        self.image = image or settings.test_runner_docker_image_go

    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 180) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        report_name = f".ai_test_review_report_{run_id}.jsonl"
        coverage_name = f".ai_test_review_cover_{run_id}.out"
        target_args = " ".join(targets) if targets else "./..."

        command = [
            "sh",
            "-c",
            f"go test -json -coverprofile={coverage_name} {target_args} > {report_name} 2>/dev/null; "
            f"go tool cover -func={coverage_name} 2>/dev/null | tail -1 || true",
        ]

        start = time.monotonic()
        try:
            image = ensure_runner_image(
                runner_image_tag(self.image, "go"), GO_RUNNER_DOCKERFILE.format(base=self.image)
            )
            proc = run_in_container(
                image=image, workspace_dir=workspace.source_dir, command=command, timeout_s=timeout_s
            )
        except Exception as e:
            return RunResult(
                run_id=run_id,
                status="error",
                total=0,
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                stderr=str(e),
            )
        duration_ms = int((time.monotonic() - start) * 1000)

        report_path = workspace.source_dir / report_name
        report_missing = not report_path.exists()
        outcomes, totals = _parse_go_json(report_path)
        # `go tool cover -func` ends with a "total:  (statements)  87.5%" line.
        coverage_percent = _parse_coverage_total(proc.stdout)

        report_path.unlink(missing_ok=True)
        (workspace.source_dir / coverage_name).unlink(missing_ok=True)

        stderr = proc.stderr[-4000:]
        if report_missing:
            stderr = _append_note(
                stderr,
                f"go test produced no JSON stream ({report_name}); the suite did not run to "
                "completion, so this run is reported as an error rather than a pass.",
            )

        return RunResult(
            run_id=run_id,
            status=overall_status(totals),
            total=totals["total"],
            passed=totals["passed"],
            failed=totals["failed"],
            errors=totals["errors"],
            skipped=totals["skipped"],
            duration_ms=duration_ms,
            outcomes=outcomes,
            coverage_percent=coverage_percent,
            stdout=proc.stdout[-4000:],
            stderr=stderr,
        )


def _append_note(stderr: str, note: str) -> str:
    return f"{stderr.rstrip()}\n{note}" if stderr.strip() else note


# `go test -json` Actions that terminate a single test.
_TERMINAL = {"pass": "passed", "fail": "failed", "skip": "skipped"}


def _parse_go_json(path: Path) -> tuple[list[TestOutcome], dict[str, int]]:
    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not path.exists():
        return [], totals

    messages: dict[str, list[str]] = {}
    outcomes: list[TestOutcome] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue  # build errors and bare text are not events
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        test = event.get("Test")
        if not test:
            continue  # package-level event, not a single test
        key = f"{event.get('Package', '')}::{test}"

        if event.get("Action") == "output":
            messages.setdefault(key, []).append(event.get("Output", ""))
            continue

        status = _TERMINAL.get(event.get("Action", ""))
        if status is None:
            continue
        outcomes.append(
            TestOutcome(
                name=key,
                status=status,
                duration_ms=int(float(event.get("Elapsed", 0) or 0) * 1000),
                message="".join(messages.get(key, [])).strip() or None if status == "failed" else None,
            )
        )
        totals["total"] += 1
        totals[status] += 1
    return outcomes, totals


def _parse_coverage_total(stdout: str) -> float | None:
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("total:") and "%" in line:
            try:
                return float(line.rsplit("%", 1)[0].rsplit(None, 1)[-1])
            except ValueError:
                return None
    return None
