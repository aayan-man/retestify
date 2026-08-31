from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.jobs import pipeline
from app.knowledge_base.schema import DeploymentIssue, PerformanceRisk, PredictedRisk
from app.knowledge_base.store import JSONFileStore

from .deps import get_workspace_or_404

router = APIRouter(prefix="/projects", tags=["risks"])


class AssessRisksRequest(BaseModel):
    company_id: str | None = None


class RiskAssessmentResponse(BaseModel):
    deployment_issues: list[DeploymentIssue]
    performance_risks: list[PerformanceRisk]
    predicted_risks: list[PredictedRisk]


@router.post("/{project_id}/assess-risks", response_model=RiskAssessmentResponse)
def assess_risks(project_id: str, body: AssessRisksRequest = AssessRisksRequest()):
    result = pipeline.assess_risks(project_id, company_id=body.company_id)
    return RiskAssessmentResponse(
        deployment_issues=result.deployment_issues,
        performance_risks=result.performance_risks,
        predicted_risks=result.predicted_risks,
    )


@router.get("/{project_id}/deployment-issues", response_model=list[DeploymentIssue])
def list_deployment_issues(project_id: str):
    return JSONFileStore().load_deployment_issues(get_workspace_or_404(project_id))


@router.get("/{project_id}/performance-risks", response_model=list[PerformanceRisk])
def list_performance_risks(project_id: str):
    return JSONFileStore().load_performance_risks(get_workspace_or_404(project_id))


@router.get("/{project_id}/predicted-risks", response_model=list[PredictedRisk])
def list_predicted_risks(project_id: str):
    return JSONFileStore().load_predicted_risks(get_workspace_or_404(project_id))
