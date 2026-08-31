from __future__ import annotations

import uuid

from app.knowledge_base.schema import Component, Recommendation, TestCase
from app.reporting.audit_log import log_event
from app.repo_manager.workspace import Workspace

from .prompts import prompt_builder
from .providers.base import LLMProvider
from .schemas import TestClassification
from .structured import complete_structured


def classify_component(
    component: Component,
    tests: list[TestCase],
    provider: LLMProvider,
    workspace: Workspace,
    change_summary: str | None = None,
) -> Recommendation:
    if not tests:
        return Recommendation(
            id=f"rec_{uuid.uuid4().hex[:10]}",
            project_id=component.project_id,
            component_id=component.id,
            related_test_ids=[],
            decision="generate",
            rationale="No existing tests map to this component.",
            confidence=1.0,
            status="pending_review",
        )

    system, user = prompt_builder.build_classification_prompt(
        component, tests, workspace.source_dir, change_summary
    )
    parsed, response = complete_structured(provider, system, user, TestClassification)

    return Recommendation(
        id=f"rec_{uuid.uuid4().hex[:10]}",
        project_id=component.project_id,
        component_id=component.id,
        related_test_ids=[t.id for t in tests],
        decision=parsed.decision,
        rationale=parsed.rationale,
        confidence=parsed.confidence,
        provider={"name": response.provider, "model": response.model},
        prompt_template="classify_test.txt#v1",
        status="pending_review",
    )


def classify_project(
    workspace: Workspace,
    provider: LLMProvider,
    components: list[Component],
    tests: list[TestCase],
) -> list[Recommendation]:
    """Classify every testable component (function/method) against its
    mapped tests. Components with no mapped tests get a "generate" decision
    without calling the LLM."""
    tests_by_component: dict[str, list[TestCase]] = {}
    for t in tests:
        for cid in t.target_component_ids:
            tests_by_component.setdefault(cid, []).append(t)

    recommendations: list[Recommendation] = []
    for component in components:
        if component.kind not in ("function", "method"):
            continue
        related = tests_by_component.get(component.id, [])
        rec = classify_component(component, related, provider, workspace)
        recommendations.append(rec)
        log_event(
            workspace,
            "recommendation_created",
            recommendation_id=rec.id,
            component_id=component.id,
            decision=rec.decision,
            confidence=rec.confidence,
        )
    return recommendations
