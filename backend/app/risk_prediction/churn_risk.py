from __future__ import annotations

import uuid

from app.knowledge_base.schema import ChangeRecord, Component, PredictedRisk

# Code-churn (modification frequency) is a well-established defect-density
# predictor — components edited repeatedly are more likely to be edited
# again, and more likely for one of those edits to introduce a bug, than
# components that have settled. This is the "if the same codebase comes
# back, what should we watch out for" signal: it only has teeth once
# `detect_changes` has run more than once for a project (changes.json now
# accumulates history — see jobs/pipeline.detect_changes).
HIGH_CHURN_THRESHOLD = 3


def _component_key(component_id: str) -> str:
    """Component ids embed a line number that shifts on unrelated edits
    (see change_detector/diff_ast.py); strip it so repeated edits to the
    "same" component are counted as the same key across snapshots."""
    return component_id.rsplit(":", 1)[0]


def compute_churn_risks(
    changes: list[ChangeRecord],
    components: list[Component],
    project_id: str,
    *,
    high_churn_threshold: int = HIGH_CHURN_THRESHOLD,
) -> list[PredictedRisk]:
    modification_counts: dict[str, int] = {}
    for change in changes:
        if change.change_type == "modified":
            modification_counts[_component_key(change.component_id)] = (
                modification_counts.get(_component_key(change.component_id), 0) + 1
            )

    current_by_key = {_component_key(c.id): c for c in components}

    risks: list[PredictedRisk] = []
    for key, count in modification_counts.items():
        if count < high_churn_threshold:
            continue
        current = current_by_key.get(key)
        if current is None:
            continue  # since deleted/renamed since; nothing left to flag
        risks.append(
            PredictedRisk(
                id=f"risk_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                component_id=current.id,
                category="high_churn",
                severity="high" if count >= high_churn_threshold * 2 else "medium",
                message=(
                    f"{current.qualified_name} has been modified {count} times in this project's tracked "
                    "history — high code churn is one of the most consistent defect-density predictors in "
                    "the literature; prioritize test coverage here."
                ),
                evidence={"modification_count": count},
            )
        )
    return risks
