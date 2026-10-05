from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from app.config import settings
from app.repo_manager.workspace import Workspace

from .base import RunResult, TestOutcome, TestRunner, overall_status
from .sandbox_exec import ensure_runner_image, run_in_container, runner_image_tag


# pytest-json-report gives a machine-readable per-test breakdown, and
# coverage supplies the before/after percentages the evaluation harness
# compares. Pinned loosely so a rebuild picks up fixes.
PYTEST_RUNNER_DOCKERFILE = """FROM {base}
RUN pip install --no-cache-dir pytest pytest-json-report coverage
"""

# Requirements-style files, in preference order. A project declaring its
# dependencies any of these ways can have them installed into the image.
REQUIREMENTS_FILES = ("requirements.txt", "requirements-dev.txt", "requirements/base.txt")
# Projects that declare dependencies through packaging metadata instead.
PACKAGE_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg")

NO_MANIFEST_HINT = (
    "The target repo declares no Python dependencies ({manifests}), so only the "
    "test tooling was available and anything the suite imports from third-party "
    "packages failed to resolve. Add a requirements.txt listing them."
)


def _dependency_layer(source_dir: Path) -> tuple[str, str] | None:
    """Dockerfile lines that install the target repo's own dependencies,
    plus a fingerprint of what they were derived from.

    Returns None when the repo declares no dependencies, in which case there
    is nothing to install and a suite importing third-party packages will
    fail with ModuleNotFoundError -- correctly, since nothing could have
    known what to install.
    """
    for name in REQUIREMENTS_FILES:
        manifest = source_dir / name
        if manifest.is_file():
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()[:12]
            # Only the manifest is copied, so an unrelated source edit does
            # not invalidate the image.
            return (
                f"COPY {name} /tmp/requirements.txt\n"
                f"RUN pip install --no-cache-dir -r /tmp/requirements.txt\n",
                digest,
            )

    for name in PACKAGE_MANIFESTS:
        manifest = source_dir / name
        if manifest.is_file():
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()[:12]
            # Packaging metadata needs the project itself to install from.
            return (
                "COPY . /src\n"
                "RUN pip install --no-cache-dir /src\n",
                digest,
            )

    return None


class PytestRunner(TestRunner):
    language = "python"

    def __init__(self, image: str | None = None):
        self.image = image or settings.test_runner_docker_image_python

    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 120) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        report_name = f".ai_test_review_report_{run_id}.json"
        coverage_name = f"{report_name}.coverage.json"
        target_args = " ".join(targets) if targets else "."

        # The tooling is baked into the image at build time. Installing it
        # here instead could never work: the run is network-isolated, so pip
        # cannot reach PyPI from inside it.
        command = [
            "sh",
            "-c",
            f"coverage run -m pytest {target_args} --json-report --json-report-file={report_name} -q; "
            f"coverage json -o {coverage_name} --quiet || true",
        ]

        dependencies = _dependency_layer(workspace.source_dir)
        dockerfile = PYTEST_RUNNER_DOCKERFILE.format(base=self.image)
        suffix = "pytest"
        if dependencies is not None:
            layer, digest = dependencies
            dockerfile += layer
            # The repo's dependencies are part of what the image *is*, so the
            # tag has to change when they do.
            suffix = f"pytest-{digest}"

        start = time.monotonic()
        try:
            image = ensure_runner_image(
                runner_image_tag(self.image, suffix),
                dockerfile,
                context_dir=workspace.source_dir if dependencies is not None else None,
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
        coverage_path = workspace.source_dir / coverage_name
        report_missing = not report_path.exists()
        outcomes, totals = _parse_json_report(report_path)
        coverage_percent = _parse_coverage(coverage_path)

        report_path.unlink(missing_ok=True)
        coverage_path.unlink(missing_ok=True)

        stderr = proc.stderr[-4000:]
        if report_missing:
            stderr = _append_note(
                stderr,
                f"pytest produced no JSON report ({report_name}); the suite did not run to "
                "completion, so this run is reported as an error rather than a pass.",
            )
            if dependencies is None:
                stderr = _append_note(
                    stderr,
                    NO_MANIFEST_HINT.format(
                        manifests=", ".join(REQUIREMENTS_FILES + PACKAGE_MANIFESTS)
                    ),
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


def _parse_json_report(path: Path) -> tuple[list[TestOutcome], dict[str, int]]:
    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not path.exists():
        return [], totals

    data = json.loads(path.read_text(encoding="utf-8"))
    outcomes: list[TestOutcome] = []
    for test in data.get("tests", []):
        status = test.get("outcome", "error")
        call = test.get("call", {}) or {}
        outcomes.append(
            TestOutcome(
                name=test.get("nodeid", "unknown"),
                status=status,
                duration_ms=int(call.get("duration", 0) * 1000),
                message=call.get("longrepr"),
            )
        )
        totals["total"] += 1
        if status in totals:
            totals[status] += 1
        else:
            totals["errors"] += 1
    return outcomes, totals


def _parse_coverage(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("totals", {}).get("percent_covered")
