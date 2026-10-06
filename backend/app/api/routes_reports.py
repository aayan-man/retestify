from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.knowledge_base.store import JSONFileStore
from app.reporting.audit_log import read_events
from app.reporting.full_report import FullReport, collect, render_html, render_markdown
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


@router.get("/{project_id}/full-report", response_model=FullReport)
def get_full_report(project_id: str) -> FullReport:
    """Everything the framework knows about this project, as structured data."""
    return collect(get_workspace_or_404(project_id))


# Content type and file extension per download format.
_FORMATS = {
    "html": ("text/html; charset=utf-8", "html"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "json": ("application/json", "json"),
}


@router.get("/{project_id}/full-report/download")
def download_full_report(project_id: str, format: str = "html") -> Response:
    """The same report as a downloadable file.

    HTML is self-contained and prints to PDF without further tooling, which
    is what makes it the default; Markdown suits pasting into a document or
    a pull request, and JSON is there for anything that wants to process the
    report rather than read it.
    """
    if format not in _FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported format {format!r}; expected one of {', '.join(_FORMATS)}",
        )
    workspace = get_workspace_or_404(project_id)
    report = collect(workspace)
    media_type, extension = _FORMATS[format]

    if format == "html":
        body = render_html(report)
    elif format == "md":
        body = render_markdown(report)
    else:
        body = report.model_dump_json(indent=2)

    filename = f"{workspace.display_name}-test-report.{extension}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
