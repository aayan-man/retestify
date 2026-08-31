from pathlib import Path

from app.deployment_testing.checker import check_deployment_readiness
from app.repo_manager.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()
    return ws


def test_flags_hardcoded_secret(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "config.py").write_text('ANTHROPIC_API_KEY = "sk-ant-abcdefghijklmnopqrstuvwx"\n', encoding="utf-8")

    issues = check_deployment_readiness(ws, "proj_test", component_count=1)

    secret_issues = [i for i in issues if i.category == "secret_exposure"]
    assert len(secret_issues) == 1
    assert secret_issues[0].severity == "high"
    assert secret_issues[0].file_path == "config.py"


def test_flags_unpinned_requirements(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "requirements.txt").write_text("requests\nflask==2.0.0\n", encoding="utf-8")

    issues = check_deployment_readiness(ws, "proj_test", component_count=1)

    pinning_issues = [i for i in issues if i.category == "dependency_pinning"]
    assert len(pinning_issues) == 1
    assert "1 dependency is unpinned" in pinning_issues[0].message


def test_flags_undocumented_env_var(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "app.py").write_text(
        'import os\nSECRET = os.getenv("STRIPE_API_TOKEN")\n', encoding="utf-8"
    )

    issues = check_deployment_readiness(ws, "proj_test", component_count=1)

    env_issues = [i for i in issues if i.category == "undocumented_env_var"]
    assert len(env_issues) == 1
    assert "STRIPE_API_TOKEN" in env_issues[0].message


def test_does_not_flag_documented_env_var(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "app.py").write_text(
        'import os\nSECRET = os.getenv("STRIPE_API_TOKEN")\n', encoding="utf-8"
    )
    (ws.source_dir / ".env.example").write_text("STRIPE_API_TOKEN=\n", encoding="utf-8")

    issues = check_deployment_readiness(ws, "proj_test", component_count=1)

    assert not [i for i in issues if i.category == "undocumented_env_var"]


def test_flags_missing_ci_only_above_component_threshold(tmp_path):
    ws = _workspace(tmp_path)

    small_repo_issues = check_deployment_readiness(ws, "proj_test", component_count=3)
    large_repo_issues = check_deployment_readiness(ws, "proj_test", component_count=15)

    assert not [i for i in small_repo_issues if i.category == "missing_ci_or_container"]
    assert [i for i in large_repo_issues if i.category == "missing_ci_or_container"]


def test_clean_repo_has_no_issues(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "requirements.txt").write_text("flask==2.0.0\n", encoding="utf-8")
    (ws.source_dir / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    issues = check_deployment_readiness(ws, "proj_test", component_count=1)
    assert issues == []
