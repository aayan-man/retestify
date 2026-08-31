from __future__ import annotations

from pydantic import BaseModel

from app.knowledge_base.schema import Recommendation
from app.test_runner.base import RunResult


class ProjectReport(BaseModel):
    project_id: str
    total_recommendations: int
    retained: int
    modified: int
    removed: int
    generated: int
    run_result: RunResult | None = None


def build_report(
    project_id: str, recommendations: list[Recommendation], run_result: RunResult | None = None
) -> ProjectReport:
    counts = {"retain": 0, "modify": 0, "remove": 0, "generate": 0}
    for rec in recommendations:
        counts[rec.decision] += 1
    return ProjectReport(
        project_id=project_id,
        total_recommendations=len(recommendations),
        retained=counts["retain"],
        modified=counts["modify"],
        removed=counts["remove"],
        generated=counts["generate"],
        run_result=run_result,
    )
