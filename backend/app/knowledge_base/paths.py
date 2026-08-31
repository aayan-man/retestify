from pathlib import Path

from app.repo_manager.workspace import Workspace


def components_path(ws: Workspace) -> Path:
    return ws.kb_dir / "components.json"


def tests_path(ws: Workspace) -> Path:
    return ws.kb_dir / "tests.json"


def changes_path(ws: Workspace) -> Path:
    return ws.kb_dir / "changes.json"


def recommendations_path(ws: Workspace) -> Path:
    return ws.kb_dir / "recommendations.json"


def audit_log_path(ws: Workspace) -> Path:
    return ws.kb_dir / "audit_log.jsonl"


def last_commit_path(ws: Workspace) -> Path:
    return ws.kb_dir / "last_commit.txt"


def deployment_issues_path(ws: Workspace) -> Path:
    return ws.kb_dir / "deployment_issues.json"


def performance_risks_path(ws: Workspace) -> Path:
    return ws.kb_dir / "performance_risks.json"


def predicted_risks_path(ws: Workspace) -> Path:
    return ws.kb_dir / "predicted_risks.json"
