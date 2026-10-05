from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.config import settings
from app.repo_manager.workspace import Workspace

from .base import RunResult, TestOutcome, TestRunner, overall_status
from .sandbox_exec import ensure_runner_image, run_in_container, runner_image_tag


JEST_RUNNER_DOCKERFILE = """FROM {base}
RUN npm install -g --no-audit --no-fund jest
"""


class JestRunner(TestRunner):
    language = "javascript"

    def __init__(self, image: str | None = None):
        self.image = image or settings.test_runner_docker_image_node

    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 180) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        report_name = f".ai_test_review_report_{run_id}.json"
        target_args = " ".join(targets) if targets else ""

        # jest is baked into the image; `npm install` here could not reach
        # the registry from a network-isolated run. A target repo whose tests
        # import its own dependencies still needs those vendored into the
        # workspace -- see the runner's module docstring.
        command = [
            "sh",
            "-c",
            f"jest {target_args} --json --outputFile={report_name} || true",
        ]

        start = time.monotonic()
        try:
            image = ensure_runner_image(
                runner_image_tag(self.image, "jest"), JEST_RUNNER_DOCKERFILE.format(base=self.image)
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
        # Jest nests its per-test records under "assertionResults"; the
        # suite's own "testResults" key does not exist in modern jest, so
        # reading it reported every run as zero tests. "testResults" is kept
        # as a fallback for older versions and jest-compatible reporters.
        for test in suite.get("assertionResults") or suite.get("testResults") or []:
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
