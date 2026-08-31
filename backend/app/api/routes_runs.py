from __future__ import annotations

from fastapi import APIRouter

from app.jobs import pipeline
from app.test_runner.base import RunResult

router = APIRouter(prefix="/projects", tags=["runs"])


@router.post("/{project_id}/run-tests", response_model=RunResult)
def run_tests(project_id: str, language: str = "python"):
    return pipeline.run_tests(project_id, language=language)
