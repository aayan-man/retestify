from __future__ import annotations

import uuid

from app.knowledge_base.schema import Component, PerformanceRisk

# Thresholds are static-analysis proxies, not measurements — they flag
# *candidates* worth benchmarking (e.g. with the existing test_runner
# extended to run pytest-benchmark/jest --testPathPattern=bench), not
# confirmed slow code. High cyclomatic complexity combined with nested
# loops is a standard "likely superlinear" heuristic; recursion without a
# name change tends to indicate no memoization guard.
NESTED_LOOP_DEPTH_THRESHOLD = 2
HIGH_COMPLEXITY_THRESHOLD = 15


def analyze_performance_risks(components: list[Component], project_id: str) -> list[PerformanceRisk]:
    risks: list[PerformanceRisk] = []
    for c in components:
        if c.kind not in ("function", "method"):
            continue

        if c.metrics.nesting_depth >= NESTED_LOOP_DEPTH_THRESHOLD and c.metrics.cyclomatic_complexity >= 4:
            risks.append(
                PerformanceRisk(
                    id=f"perf_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    component_id=c.id,
                    category="nested_loops",
                    severity="medium",
                    message=(
                        f"{c.qualified_name} has nesting depth {c.metrics.nesting_depth} and cyclomatic "
                        f"complexity {c.metrics.cyclomatic_complexity} — a plausible O(n^2)+ hot path; "
                        "worth a benchmark test with a realistic input size."
                    ),
                )
            )

        if c.metrics.cyclomatic_complexity >= HIGH_COMPLEXITY_THRESHOLD:
            risks.append(
                PerformanceRisk(
                    id=f"perf_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    component_id=c.id,
                    category="high_complexity_hot_path",
                    severity="low",
                    message=(
                        f"{c.qualified_name} has cyclomatic complexity {c.metrics.cyclomatic_complexity} — "
                        "high branch count is correlated with both defect rate and unpredictable runtime; "
                        "a good candidate for both more tests and a benchmark."
                    ),
                )
            )

        if c.name in c.calls:
            risks.append(
                PerformanceRisk(
                    id=f"perf_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    component_id=c.id,
                    category="unbounded_recursion",
                    severity="medium",
                    message=(
                        f"{c.qualified_name} calls itself — verify it has a base case and, if it recomputes "
                        "overlapping subproblems, consider memoization before it's exercised at scale."
                    ),
                )
            )

    return risks
