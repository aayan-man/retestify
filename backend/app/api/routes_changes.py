from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.jobs import pipeline
from app.knowledge_base.schema import ChangeRecord, Recommendation
from app.knowledge_base.store import JSONFileStore

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["changes"])


class ProviderOverride(BaseModel):
    provider: str | None = None


@router.post("/{project_id}/detect-changes", response_model=list[ChangeRecord])
def detect_changes(project_id: str):
    return pipeline.detect_changes(project_id)


@router.post("/{project_id}/classify-changed", response_model=list[Recommendation])
def classify_changed(project_id: str, body: ProviderOverride = ProviderOverride()):
    return pipeline.classify_changed_components(project_id, provider_name=body.provider)


@router.get("/{project_id}/changes", response_model=list[ChangeRecord])
def list_changes(project_id: str):
    return JSONFileStore().load_changes(get_workspace_or_404(project_id))
