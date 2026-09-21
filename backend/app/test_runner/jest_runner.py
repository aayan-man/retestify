from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.config import settings
from app.repo_manager.workspace import Workspace

from .base import RunResult, TestOutcome, TestRunner, overall_status
from .sandbox_exec import run_in_container


class JestRunner(TestRunner):
    language = "javascript"

    def __init__(self, image: str | None = None):
        self.image = image or settings.test_runner_docker_image_node

    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 180) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        report_name = f".ai_test_review_report_{run_id}.json"
        target_args = " ".join(targets) if targets else ""

        command = [
            "sh",
            "-c",
            "npm install --no-audit --no-fund -q >/dev/null 2>&1; "
            f"npx --yes jest {target_args} --json --outputFile={report_name} || true",
        ]

        start = time.monotonic()
        try:
            proc = run_in_container(
                image=self.image, workspace_dir=workspace.source_dir, command=command, timeout_s=timeout_s
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
        outcomes, totals = _parse_jest_report(report_path)
        report_path.unlink(missing_ok=True)

        stderr = proc.stderr[-4000:]
        if report_missing:
            stderr = _append_note(
                stderr,
                f"jest produced no JSON report ({report_name}); the suite did not run to "
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
            coverage_percent=None,  # requires a separate --coverage summary pass; not wired up yet
            stdout=proc.stdout[-4000:],
            stderr=stderr,
        )


def _append_note(stderr: str, note: str) -> str:
    return f"{stderr.rstrip()}\n{note}" if stderr.strip() else note


def _parse_jest_report(path: Path) -> tuple[list[TestOutcome], dict[str, int]]:
    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not path.exists():
        return [], totals

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], totals

    outcomes: list[TestOutcome] = []
    for suite in data.get("testResults", []):
        for test in suite.get("testResults", []):
            raw_status = test.get("status", "failed")
            status = "passed" if raw_status == "passed" else ("skipped" if raw_status == "pending" else "failed")
            outcomes.append(
                TestOutcome(
                    name=test.get("fullName", "unknown"),
                    status=status,
                    duration_ms=int(test.get("duration") or 0),
                    message="\n".join(test.get("failureMessages", [])) or None,
                )
            )
            totals["total"] += 1
            totals[status] += 1
    return outcomes, totals
