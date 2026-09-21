from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.ai_engine import decision_engine, generator
from app.ai_engine.providers.factory import require_provider
from app.analyzers.registry import detect_all
from app.change_detector import diff_ast, impact
from app.deployment_testing.checker import check_deployment_readiness
from app.git_integration import repo as git_repo
from app.knowledge_base import paths as kb_paths
from app.knowledge_base.schema import (
    ChangeRecord,
    Component,
    DeploymentIssue,
    PerformanceRisk,
    PredictedRisk,
    Recommendation,
    TestCase,
)
from app.knowledge_base.store import JSONFileStore
from app.performance_testing.risk_analyzer import analyze_performance_risks
from app.personalization.profile import CompanyProfile, load_company_profile
from app.reporting.audit_log import log_event
from app.repo_manager import ingest
from app.repo_manager.workspace import Workspace, load_workspace
from app.risk_prediction.churn_risk import compute_churn_risks
from app.risk_prediction.pattern_detector import detect_code_smells
from app.tech_detector.detector import StackProfile, detect_stack

logger = logging.getLogger(__name__)

# Called with (processed, total) as a long-running call advances.
ProgressCallback = Callable[[int, int], None]
from app.test_analyzer.discover import extract_test_cases
from app.test_analyzer.mapper import map_components_to_tests
from app.test_runner.base import RunResult
from app.test_runner.registry import get_runner
from app.test_writer.registry import get_writer


@dataclass
class AnalysisSummary:
    workspace: Workspace
    stack: StackProfile
    component_count: int
    test_count: int
    mapped_test_count: int
    parse_errors: list[str]


def ingest_source(
    *, path: str | None = None, github_url: str | None = None, ref: str | None = None
) -> Workspace:
    """The single ingestion entrypoint used by the CLI, the future REST API, and
    the evaluation harness alike, so all callers land on the same Workspace shape."""
    if github_url:
        return ingest.clone_github(github_url, ref=ref)
    if path:
        p = Path(path)
        if p.is_dir():
            return ingest.import_directory(p)
        return ingest.extract_zip(p)
    raise ValueError("either path or github_url must be provided")


def analyze(workspace: Workspace) -> AnalysisSummary:
    stack = detect_stack(workspace)
    analyzers = detect_all(workspace)
    store = JSONFileStore()
    framework_by_language = _framework_map(stack)

    all_components: list[Component] = []
    all_parse_errors: list[str] = []
    for analyzer in analyzers:
        for file_path in analyzer.list_source_files(workspace):
            if analyzer.is_test_file(file_path):
                continue
            result = analyzer.parse(file_path, project_id=workspace.project_id, root=workspace.source_dir)
            all_components.extend(result.components)
            all_parse_errors.extend(result.parse_errors)
    store.save_components(workspace, all_components)

    all_tests = []
    for analyzer in analyzers:
        framework = framework_by_language.get(analyzer.language, "unknown")
        all_tests.extend(extract_test_cases(workspace, analyzer, workspace.project_id, framework))

    mapped_tests = map_components_to_tests(all_components, all_tests)
    store.save_tests(workspace, mapped_tests)

    if git_repo.is_git_repo(workspace):
        kb_paths.last_commit_path(workspace).write_text(git_repo.current_commit(workspace), encoding="utf-8")

    return AnalysisSummary(
        workspace=workspace,
        stack=stack,
        component_count=len(all_components),
        test_count=len(mapped_tests),
        mapped_test_count=sum(1 for t in mapped_tests if t.target_component_ids),
        parse_errors=all_parse_errors,
    )


def classify_project(project_id: str, provider_name: str | None = None) -> list[Recommendation]:
    """Run the AI Review Engine's read-only classification (retain/modify/
    remove/generate) over every analyzed component and persist the result."""
    workspace = load_workspace(project_id)
    store = JSONFileStore()
    components = store.load_components(workspace)
    tests = store.load_tests(workspace)

    provider = require_provider(provider_name)
    recommendations = decision_engine.classify_project(workspace, provider, components, tests)
    store.save_recommendations(workspace, recommendations)
    return recommendations


def apply_recommendations(
    project_id: str,
    provider_name: str | None = None,
    company_id: str | None = None,
    progress: ProgressCallback | None = None,
) -> list[Recommendation]:
    """For each pending "generate" or "modify" recommendation, have the AI
    engine write a test to disk (as a new test function — existing test
    files are never rewritten in place) and mark the recommendation applied.

    `company_id`, if given, loads a CompanyProfile (see app/personalization)
    whose style_guide is injected into the generation/improvement prompts —
    the personalization lever for per-organization conventions.

    `progress(processed, total)` is called after each recommendation the
    engine actually works on, so a caller running this as a background job
    can report how far along it is."""
    workspace = load_workspace(project_id)
    store = JSONFileStore()
    components_by_id = {c.id: c for c in store.load_components(workspace)}
    tests = store.load_tests(workspace)
    recommendations = store.load_recommendations(workspace)

    provider = require_provider(provider_name)
    company_profile: CompanyProfile | None = load_company_profile(company_id) if company_id else None
    stack = detect_stack(workspace)
    framework_by_language = _framework_map(stack)

    updated_recommendations: list[Recommendation] = []
    all_tests: list[TestCase] = list(tests)

    actionable = sum(
        1
        for rec in recommendations
        if rec.status == "pending_review"
        and rec.decision in ("generate", "modify")
        and rec.component_id in components_by_id
    )
    processed = 0
    if progress is not None:
        progress(0, actionable)

    for rec in recommendations:
        component = components_by_id.get(rec.component_id)
        if component is None or rec.status != "pending_review" or rec.decision not in ("generate", "modify"):
            updated_recommendations.append(rec)
            continue

        framework = framework_by_language.get(component.language, "unknown")
        writer = get_writer(component.language)

        try:
            if rec.decision == "generate":
                generated = generator.generate_test(component, provider, workspace, framework, company_profile)
            else:
                original_test = next((t for t in tests if t.id in rec.related_test_ids), None)
                if original_test is None:
                    updated_recommendations.append(rec)
                    processed += 1
                    if progress is not None:
                        progress(processed, actionable)
                    continue
                generated = generator.improve_test(
                    component, original_test, rec.rationale, provider, workspace, framework, company_profile
                )

            new_test = writer(workspace, component, generated, framework)
        except Exception as e:
            # One component the model can't write a usable test for must not
            # discard the tests already generated in this run — applying is a
            # long, paid-for loop and results are only persisted after it.
            logger.warning("Could not apply recommendation %s (%s): %s", rec.id, rec.component_id, e)
            updated_recommendations.append(
                rec.model_copy(update={"status": "failed", "failure_reason": str(e)})
            )
            processed += 1
            if progress is not None:
                progress(processed, actionable)
            continue

        if rec.decision == "modify":
            new_test = new_test.model_copy(update={"origin": "ai_modified"})
        all_tests.append(new_test)

        rec = rec.model_copy(
            update={"generated_code": generated.code, "generated_test_id": new_test.id, "status": "applied"}
        )
        updated_recommendations.append(rec)
        log_event(
            workspace,
            "test_written",
            recommendation_id=rec.id,
            test_id=new_test.id,
            origin=new_test.origin,
            file_path=new_test.file_path,
        )
        processed += 1
        if progress is not None:
            progress(processed, actionable)

    store.save_tests(workspace, all_tests)
    store.save_recommendations(workspace, updated_recommendations)
    return updated_recommendations


def detect_changes(project_id: str) -> list[ChangeRecord]:
    """Pull the target repo's latest commits, re-analyze at the new HEAD,
    and diff against the previously stored knowledge base to find what
    was added/modified/deleted (and what else might be impacted)."""
    workspace = load_workspace(project_id)
    store = JSONFileStore()

    old_components = store.load_components(workspace)
    old_tests = store.load_tests(workspace)
    last_commit_file = kb_paths.last_commit_path(workspace)
    from_commit = last_commit_file.read_text(encoding="utf-8").strip() if last_commit_file.exists() else None

    to_commit = git_repo.pull_latest(workspace)
    analyze(workspace)  # re-analyze at new HEAD; overwrites components.json/tests.json and last_commit.txt

    new_components = store.load_components(workspace)
    changes = diff_ast.detect_changes(project_id, old_components, new_components, old_tests, from_commit, to_commit)
    changes = impact.propagate_impact(changes, new_components)

    # Append rather than overwrite: churn-based risk prediction (how many
    # times has this component actually changed?) needs the full history,
    # not just the latest diff — see risk_prediction/churn_risk.py.
    history = store.load_changes(workspace)
    store.save_changes(workspace, history + changes)

    log_event(workspace, "changes_detected", from_commit=from_commit, to_commit=to_commit, count=len(changes))
    return changes


def classify_changed_components(project_id: str, provider_name: str | None = None) -> list[Recommendation]:
    """Incremental analysis: reclassify only the components touched or
    impacted by the most recently detected change set, instead of the
    whole project."""
    workspace = load_workspace(project_id)
    store = JSONFileStore()
    changes = store.load_changes(workspace)
    if not changes:
        return []

    affected_ids = impact.affected_component_ids(changes)
    change_by_component = {c.component_id: c for c in changes}
    components = {c.id: c for c in store.load_components(workspace)}

    tests_by_component: dict[str, list[TestCase]] = {}
    for t in store.load_tests(workspace):
        for cid in t.target_component_ids:
            tests_by_component.setdefault(cid, []).append(t)

    provider = require_provider(provider_name)
    new_recommendations: list[Recommendation] = []
    for comp_id in affected_ids:
        component = components.get(comp_id)
        if component is None or component.kind not in ("function", "method"):
            continue
        related = tests_by_component.get(comp_id, [])
        change = change_by_component.get(comp_id)
        summary = change.diff_summary if change else "impacted by a nearby change"
        rec = decision_engine.classify_component(component, related, provider, workspace, change_summary=summary)
        new_recommendations.append(rec)
        log_event(
            workspace,
            "recommendation_created",
            recommendation_id=rec.id,
            component_id=component.id,
            decision=rec.decision,
            confidence=rec.confidence,
            incremental=True,
        )

    existing = store.load_recommendations(workspace)
    merged = [r for r in existing if r.component_id not in affected_ids] + new_recommendations
    store.save_recommendations(workspace, merged)
    return new_recommendations


@dataclass
class RiskAssessment:
    deployment_issues: list[DeploymentIssue]
    performance_risks: list[PerformanceRisk]
    predicted_risks: list[PredictedRisk]


def assess_risks(project_id: str, company_id: str | None = None) -> RiskAssessment:
    """Deployment-readiness checks, static performance-risk flags, and
    defect-proneness prediction (structural code smells + historical
    modification frequency) — all static, no code execution required.
    Re-running this on the same project after `detect_changes` has
    accumulated more history sharpens the churn signal, directly answering
    "what problems is this codebase likely to face again"."""
    workspace = load_workspace(project_id)
    store = JSONFileStore()
    components = store.load_components(workspace)
    changes = store.load_changes(workspace)

    company_profile = load_company_profile(company_id) if company_id else None
    complexity_threshold = company_profile.complexity_risk_threshold if company_profile else 10
    churn_threshold = company_profile.churn_risk_threshold if company_profile else 3

    deployment_issues = check_deployment_readiness(workspace, project_id, len(components))
    performance_risks = analyze_performance_risks(components, project_id)
    predicted_risks = detect_code_smells(
        components, project_id, god_method_complexity=complexity_threshold
    ) + compute_churn_risks(changes, components, project_id, high_churn_threshold=churn_threshold)

    store.save_deployment_issues(workspace, deployment_issues)
    store.save_performance_risks(workspace, performance_risks)
    store.save_predicted_risks(workspace, predicted_risks)

    log_event(
        workspace,
        "risk_assessment_completed",
        deployment_issues=len(deployment_issues),
        performance_risks=len(performance_risks),
        predicted_risks=len(predicted_risks),
        company_id=company_id,
    )
    return RiskAssessment(
        deployment_issues=deployment_issues, performance_risks=performance_risks, predicted_risks=predicted_risks
    )


def run_tests(project_id: str, language: str = "python") -> RunResult:
    workspace = load_workspace(project_id)
    runner = get_runner(language)
    result = runner.run(workspace)
    log_event(
        workspace,
        "test_run_completed",
        run_id=result.run_id,
        status=result.status,
        passed=result.passed,
        failed=result.failed,
        coverage_percent=result.coverage_percent,
    )
    return result


def _framework_map(stack: StackProfile) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if "python" in stack.languages:
        mapping["python"] = "pytest" if "pytest" in stack.test_frameworks else "unittest"
    if "javascript" in stack.languages or "typescript" in stack.languages:
        if "jest" in stack.test_frameworks:
            fw = "jest"
        elif "mocha" in stack.test_frameworks:
            fw = "mocha"
        else:
            fw = "unknown"
        mapping["javascript"] = fw
        mapping["typescript"] = fw
    if "java" in stack.languages:
        mapping["java"] = "junit"
    if "cpp" in stack.languages:
        mapping["cpp"] = "catch2" if "catch2" in stack.test_frameworks else "gtest"
    if "go" in stack.languages:
        mapping["go"] = "testing"
    if "csharp" in stack.languages:
        if "nunit" in stack.test_frameworks:
            mapping["csharp"] = "nunit"
        elif "mstest" in stack.test_frameworks:
            mapping["csharp"] = "mstest"
        else:
            mapping["csharp"] = "xunit"
    return mapping
