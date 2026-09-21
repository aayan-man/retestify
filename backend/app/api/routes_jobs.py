from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.jobs.queue import Job, queue

from .deps import get_workspace_or_404

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return job


@router.get("/projects/{project_id}/jobs", response_model=list[Job])
def list_project_jobs(project_id: str) -> list[Job]:
    get_workspace_or_404(project_id)
    return queue.list_for_project(project_id)
