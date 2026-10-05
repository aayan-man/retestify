from __future__ import annotations

from fastapi import APIRouter

from app.knowledge_base.store import JSONFileStore
from app.reporting.audit_log import read_events
from app.reporting.report_builder import ProjectReport, build_report

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["reports"])


@router.get("/{project_id}/report", response_model=ProjectReport)
def get_report(project_id: str):
    workspace = get_workspace_or_404(project_id)
    store = JSONFileStore()
    recommendations = store.load_recommendations(workspace)
    runs = store.load_runs(workspace)
    # Latest run only: the report answers "where does this project stand now".
    return build_report(project_id, recommendations, runs[-1] if runs else None)


@router.get("/{project_id}/audit-log")
def get_audit_log(project_id: str) -> list[dict]:
    return read_events(get_workspace_or_404(project_id))
