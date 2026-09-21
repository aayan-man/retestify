from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.ai_engine.providers.factory import require_provider
from app.jobs import pipeline
from app.jobs.queue import Job, queue
from app.knowledge_base.schema import Recommendation
from app.knowledge_base.store import JSONFileStore

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["recommendations"])


class ProviderOverride(BaseModel):
    provider: str | None = None


class ApplyRequest(BaseModel):
    provider: str | None = None
    company_id: str | None = None


def _counts(recommendations: list[Recommendation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in recommendations:
        counts[rec.status] = counts.get(rec.status, 0) + 1
    return counts


@router.post("/{project_id}/classify", response_model=Job, status_code=202)
def classify(project_id: str, response: Response, body: ProviderOverride = ProviderOverride()) -> Job:
    """Start classification in the background and return the job to poll.

    Classification is one LLM call per component, so it is returned as a
    202 job rather than held open for the length of the run — see
    app/jobs/queue.py. Poll GET /jobs/{id}, then read the results from
    GET /projects/{id}/recommendations as usual.
    """
    get_workspace_or_404(project_id)
    # Check configuration before queueing: a missing API key should still be
    # an immediate, readable 400 rather than a job that accepts and then
    # fails.
    require_provider(body.provider)

    def run(progress):
        recommendations = pipeline.classify_project(project_id, provider_name=body.provider)
        progress(len(recommendations), len(recommendations))
        return {"recommendations": len(recommendations), **_counts(recommendations)}

    job = queue.submit(project_id, "classify", run)
    response.headers["Location"] = f"/jobs/{job.id}"
    return job


@router.post("/{project_id}/apply", response_model=Job, status_code=202)
def apply(project_id: str, response: Response, body: ApplyRequest = ApplyRequest()) -> Job:
    """Start applying pending recommendations in the background.

    This writes one generated test per recommendation and routinely runs
    for minutes, which is why it is a job rather than a blocking request.
    """
    get_workspace_or_404(project_id)
    require_provider(body.provider)

    def run(progress):
        recommendations = pipeline.apply_recommendations(
            project_id,
            provider_name=body.provider,
            company_id=body.company_id,
            progress=progress,
        )
        return {"recommendations": len(recommendations), **_counts(recommendations)}

    job = queue.submit(project_id, "apply", run)
    response.headers["Location"] = f"/jobs/{job.id}"
    return job


@router.get("/{project_id}/recommendations", response_model=list[Recommendation])
def list_recommendations(project_id: str):
    return JSONFileStore().load_recommendations(get_workspace_or_404(project_id))
