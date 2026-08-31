from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.jobs import pipeline
from app.knowledge_base.schema import Recommendation
from app.knowledge_base.store import JSONFileStore

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["recommendations"])


class ProviderOverride(BaseModel):
    provider: str | None = None


@router.post("/{project_id}/classify", response_model=list[Recommendation])
def classify(project_id: str, body: ProviderOverride = ProviderOverride()):
    return pipeline.classify_project(project_id, provider_name=body.provider)


@router.post("/{project_id}/apply", response_model=list[Recommendation])
def apply(project_id: str, body: ProviderOverride = ProviderOverride()):
    return pipeline.apply_recommendations(project_id, provider_name=body.provider)


@router.get("/{project_id}/recommendations", response_model=list[Recommendation])
def list_recommendations(project_id: str):
    return JSONFileStore().load_recommendations(get_workspace_or_404(project_id))
