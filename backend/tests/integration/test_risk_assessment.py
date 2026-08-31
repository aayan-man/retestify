import shutil
import subprocess
from pathlib import Path

from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_assess_risks_runs_and_persists_to_kb():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        assessment = pipeline.assess_risks(workspace.project_id)

        assert isinstance(assessment.deployment_issues, list)
        assert isinstance(assessment.performance_risks, list)
        assert isinstance(assessment.predicted_risks, list)

        store = JSONFileStore()
        assert store.load_deployment_issues(workspace) == assessment.deployment_issues
        assert store.load_performance_risks(workspace) == assessment.performance_risks
        assert store.load_predicted_risks(workspace) == assessment.predicted_risks
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def test_assess_risks_with_company_profile_uses_lower_thresholds():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        default = pipeline.assess_risks(workspace.project_id)
        # example-corp.json sets complexity_risk_threshold=8 (default is 10)
        personalized = pipeline.assess_risks(workspace.project_id, company_id="example-corp")

        assert len(personalized.predicted_risks) >= len(default.predicted_risks)
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def _init_local_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    _run_git(["init", "-q"], origin)
    _run_git(["config", "user.email", "test@example.com"], origin)
    _run_git(["config", "user.name", "Test"], origin)
    (origin / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _run_git(["add", "."], origin)
    _run_git(["commit", "-q", "-m", "initial"], origin)
    return origin


def test_repeated_changes_accumulate_into_high_churn_risk(tmp_path):
    origin = _init_local_repo(tmp_path)
    workspace = pipeline.ingest_source(github_url=str(origin))
    try:
        pipeline.analyze(workspace)

        for i in range(3):
            (origin / "calc.py").write_text(f"def add(a, b):\n    return a + b + {i}\n", encoding="utf-8")
            _run_git(["add", "."], origin)
            _run_git(["commit", "-q", "-m", f"edit {i}"], origin)
            pipeline.detect_changes(workspace.project_id)

        # this project's own analyze() also runs during each detect_changes,
        # so the KB reflects the latest snapshot with accumulated history
        assessment = pipeline.assess_risks(workspace.project_id, company_id=None)
        churn_risks = [r for r in assessment.predicted_risks if r.category == "high_churn"]
        assert len(churn_risks) == 1
        assert churn_risks[0].evidence["modification_count"] == 3
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
