from __future__ import annotations

import uuid

from app.knowledge_base.schema import Component, PredictedRisk

# Thresholds follow the code-smell/defect-prediction literature's most
# consistently effective smells (God Class, God Method, long parameter
# list, deep nesting) rather than being tuned per-project — see
# docs/PROJECT_GUIDE_QA.md for citations. A `CompanyProfile` (see
# app/personalization) can override these per organization.
GOD_CLASS_METHOD_COUNT = 10
GOD_METHOD_LOC = 50
GOD_METHOD_COMPLEXITY = 10
LONG_PARAMETER_LIST = 5
DEEP_NESTING = 4


def detect_code_smells(
    components: list[Component],
    project_id: str,
    *,
    god_class_method_count: int = GOD_CLASS_METHOD_COUNT,
    god_method_loc: int = GOD_METHOD_LOC,
    god_method_complexity: int = GOD_METHOD_COMPLEXITY,
    long_parameter_list: int = LONG_PARAMETER_LIST,
    deep_nesting: int = DEEP_NESTING,
) -> list[PredictedRisk]:
    """Flag components matching structural patterns the defect-prediction
    literature associates with elevated bug rates — a prediction of what
    this codebase is likely to face, not a report of what already broke."""
    risks: list[PredictedRisk] = []
    method_counts: dict[str, int] = {}
    for c in components:
        if c.kind == "method" and c.parent_id:
            method_counts[c.parent_id] = method_counts.get(c.parent_id, 0) + 1

    for c in components:
        if c.kind == "class":
            count = method_counts.get(c.id, 0)
            if count >= god_class_method_count:
                risks.append(
                    _risk(
                        project_id, c, "god_class", "medium",
                        f"{c.qualified_name} has {count} methods — a God Class is one of the smells most "
                        "consistently linked to higher defect density; consider splitting responsibilities.",
                        {"method_count": count},
                    )
                )
            continue

        if c.kind not in ("function", "method"):
            continue

        if c.metrics.loc >= god_method_loc and c.metrics.cyclomatic_complexity >= god_method_complexity:
            risks.append(
                _risk(
                    project_id, c, "god_method", "medium",
                    f"{c.qualified_name} is {c.metrics.loc} LOC with cyclomatic complexity "
                    f"{c.metrics.cyclomatic_complexity} — God Method smell; historically one of the strongest "
                    "smell-based defect predictors.",
                    {"loc": c.metrics.loc, "cyclomatic_complexity": c.metrics.cyclomatic_complexity},
                )
            )

        if c.metrics.num_params >= long_parameter_list:
            risks.append(
                _risk(
                    project_id, c, "long_parameter_list", "low",
                    f"{c.qualified_name} takes {c.metrics.num_params} parameters — long parameter lists "
                    "correlate with harder-to-test call sites and misordered-argument bugs.",
                    {"num_params": c.metrics.num_params},
                )
            )

        if c.metrics.nesting_depth >= deep_nesting:
            risks.append(
                _risk(
                    project_id, c, "deep_nesting", "low",
                    f"{c.qualified_name} has nesting depth {c.metrics.nesting_depth} — deeply nested control "
                    "flow is harder to reason about and to get full branch coverage on.",
                    {"nesting_depth": c.metrics.nesting_depth},
                )
            )

    return risks


def _risk(project_id: str, c: Component, category: str, severity: str, message: str, evidence: dict) -> PredictedRisk:
    return PredictedRisk(
        id=f"risk_{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        component_id=c.id,
        category=category,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=message,
        evidence=evidence,
    )
