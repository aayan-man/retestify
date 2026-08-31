from __future__ import annotations

import time

from app.ai_engine import decision_engine
from app.ai_engine.providers.factory import get_provider
from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore

from .cost_tracking import CostTrackingProvider
from .metrics import RunMetrics, summarize_decisions


def run_framework(
    repo_path: str | None = None,
    github_url: str | None = None,
    provider_name: str | None = None,
    language: str = "python",
) -> RunMetrics:
    """The framework's own arm: ingest -> analyze -> classify -> apply ->
    run tests, measuring coverage before and after AI-driven generation."""
    provider = CostTrackingProvider(get_provider(provider_name))
    start = time.monotonic()

    workspace = pipeline.ingest_source(path=repo_path, github_url=github_url)
    summary = pipeline.analyze(workspace)

    store = JSONFileStore()
    components = store.load_components(workspace)
    tests = store.load_tests(workspace)
    recommendations = decision_engine.classify_project(workspace, provider, components, tests)
    store.save_recommendations(workspace, recommendations)

    coverage_before = pipeline.run_tests(workspace.project_id, language=language).coverage_percent
    pipeline.apply_recommendations(workspace.project_id, provider_name=provider_name)
    coverage_after = pipeline.run_tests(workspace.project_id, language=language).coverage_percent

    elapsed = time.monotonic() - start
    return RunMetrics(
        repo=github_url or repo_path or "unknown",
        variant="framework",
        execution_time_s=elapsed,
        component_count=summary.component_count,
        test_count=summary.test_count,
        mapped_test_count=summary.mapped_test_count,
        recommendations_count=len(recommendations),
        decision_counts=summarize_decisions(recommendations),
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        total_input_tokens=provider.total_input_tokens,
        total_output_tokens=provider.total_output_tokens,
    )
