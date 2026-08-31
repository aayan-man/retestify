from __future__ import annotations

import time

from app.jobs import pipeline

from .metrics import RunMetrics


def run_manual_baseline(
    repo_path: str | None = None, github_url: str | None = None, language: str = "python"
) -> RunMetrics:
    """The 'traditional testing' comparison arm: no AI involvement at all —
    just ingest, statically analyze, and run whatever tests already exist
    in the repo as-is."""
    start = time.monotonic()
    workspace = pipeline.ingest_source(path=repo_path, github_url=github_url)
    summary = pipeline.analyze(workspace)
    run_result = pipeline.run_tests(workspace.project_id, language=language)
    elapsed = time.monotonic() - start

    return RunMetrics(
        repo=github_url or repo_path or "unknown",
        variant="manual_baseline",
        execution_time_s=elapsed,
        component_count=summary.component_count,
        test_count=summary.test_count,
        mapped_test_count=summary.mapped_test_count,
        recommendations_count=0,
        coverage_before=run_result.coverage_percent,
        coverage_after=run_result.coverage_percent,
    )
