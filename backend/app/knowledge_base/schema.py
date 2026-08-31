from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ComponentMetrics(BaseModel):
    loc: int
    cyclomatic_complexity: int
    nesting_depth: int
    num_params: int = 0


class Component(BaseModel):
    """A function, method, or class extracted from the target repo's source."""

    id: str
    project_id: str
    language: str
    kind: Literal["function", "method", "class"]
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    parent_id: str | None = None
    imports_used: list[str] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)
    metrics: ComponentMetrics
    content_hash: str
    source_commit: str | None = None
    extracted_at: datetime = Field(default_factory=utcnow)


class TestRunResult(BaseModel):
    status: Literal["passed", "failed", "error", "skipped"]
    duration_ms: int
    run_id: str
    ran_at: datetime


class TestCase(BaseModel):
    """A discovered (or AI-generated) test function/method."""

    __test__ = False  # not a pytest test class, despite the name

    id: str
    project_id: str
    language: str
    framework: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    target_component_ids: list[str] = Field(default_factory=list)
    mapping_method: Literal["naming_convention", "import_graph", "coverage", "unmapped"] = "unmapped"
    mapping_confidence: float = 0.0
    last_run: TestRunResult | None = None
    covers_lines: list[int] = Field(default_factory=list)
    content_hash: str
    origin: Literal["existing", "ai_generated", "ai_modified"] = "existing"


class ChangeRecord(BaseModel):
    """A detected add/modify/delete of a component between two commits."""

    id: str
    project_id: str
    from_commit: str | None = None
    to_commit: str | None = None
    detected_at: datetime = Field(default_factory=utcnow)
    component_id: str
    change_type: Literal["added", "modified", "deleted"]
    diff_summary: str | None = None
    old_content_hash: str | None = None
    new_content_hash: str | None = None
    affected_test_ids: list[str] = Field(default_factory=list)
    impact_propagated_to: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """An AI Review Engine decision about a component's test coverage."""

    id: str
    project_id: str
    component_id: str
    related_test_ids: list[str] = Field(default_factory=list)
    decision: Literal["retain", "modify", "remove", "generate"]
    rationale: str
    confidence: float
    triggered_by_change_id: str | None = None
    provider: dict | None = None
    prompt_template: str | None = None
    generated_code: str | None = None
    generated_test_id: str | None = None
    status: Literal["pending_review", "accepted", "rejected", "applied"] = "pending_review"
    created_at: datetime = Field(default_factory=utcnow)
    reviewed_by: str | None = None
    linked_run_id: str | None = None
    linked_coverage_delta: float | None = None
