from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.jobs import pipeline
from app.jobs.pipeline import AnalysisSummary
from app.knowledge_base.schema import Component, TestCase
from app.knowledge_base.store import JSONFileStore
from app.repo_manager.export import build_zip_bytes

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["projects"])


class IngestGithubRequest(BaseModel):
    github_url: str
    ref: str | None = None


class ProjectSummary(BaseModel):
    project_id: str
    languages: list[str]
    frameworks: list[str]
    component_count: int
    test_count: int
    mapped_test_count: int
    parse_error_count: int


def _to_summary(summary: AnalysisSummary) -> ProjectSummary:
    return ProjectSummary(
        project_id=summary.workspace.project_id,
        languages=summary.stack.languages,
        frameworks=summary.stack.test_frameworks,
        component_count=summary.component_count,
        test_count=summary.test_count,
        mapped_test_count=summary.mapped_test_count,
        parse_error_count=len(summary.parse_errors),
    )


@router.post("", response_model=ProjectSummary)
def create_project_from_github(body: IngestGithubRequest) -> ProjectSummary:
    workspace = pipeline.ingest_source(github_url=body.github_url, ref=body.ref)
    return _to_summary(pipeline.analyze(workspace))


@router.post("/upload", response_model=ProjectSummary)
async def create_project_from_zip(file: UploadFile) -> ProjectSummary:
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="only .zip uploads are supported")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / file.filename
        zip_path.write_bytes(await file.read())
        workspace = pipeline.ingest_source(path=str(zip_path))
    return _to_summary(pipeline.analyze(workspace))


@router.get("/{project_id}/components", response_model=list[Component])
def list_components(project_id: str):
    return JSONFileStore().load_components(get_workspace_or_404(project_id))


@router.get("/{project_id}/tests", response_model=list[TestCase])
def list_tests(project_id: str):
    return JSONFileStore().load_tests(get_workspace_or_404(project_id))


@router.get("/{project_id}/download")
def download_project(project_id: str) -> Response:
    """Re-zip the project's current workspace (source + any AI-generated
    test files written into it) so it can be downloaded — the workspace is
    server-side storage only and otherwise never leaves the backend."""
    workspace = get_workspace_or_404(project_id)
    zip_bytes = build_zip_bytes(workspace)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'},
    )
