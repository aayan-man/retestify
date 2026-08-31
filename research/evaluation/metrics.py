from __future__ import annotations

from dataclasses import dataclass, field

from app.knowledge_base.schema import Recommendation


@dataclass
class RunMetrics:
    repo: str
    variant: str  # "framework" | "manual_baseline" | "standalone_llm_baseline"
    execution_time_s: float
    component_count: int
    test_count: int
    mapped_test_count: int
    recommendations_count: int
    decision_counts: dict[str, int] = field(default_factory=dict)
    coverage_before: float | None = None
    coverage_after: float | None = None
    accuracy: float | None = None  # only set when a ground-truth mapping is supplied
    total_input_tokens: int = 0
    total_output_tokens: int = 0


def coverage_delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return after - before


def compute_accuracy(recommendations: list[Recommendation], ground_truth: dict[str, str]) -> float | None:
    """Compares each recommendation's decision against a human-labeled
    ground_truth mapping (component_id -> expected decision). Returns None
    when no ground truth is supplied for a repo — there's no programmatic
    way to know the "correct" retain/modify/remove/generate call otherwise,
    so this metric is intentionally absent rather than faked."""
    if not ground_truth:
        return None
    labeled = [r for r in recommendations if r.component_id in ground_truth]
    if not labeled:
        return None
    correct = sum(1 for r in labeled if r.decision == ground_truth[r.component_id])
    return correct / len(labeled)


def summarize_decisions(recommendations: list[Recommendation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in recommendations:
        counts[r.decision] = counts.get(r.decision, 0) + 1
    return counts
