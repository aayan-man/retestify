from app.knowledge_base.schema import Component, TestCase

from . import heuristics as h

CONFIDENCE_THRESHOLD = 0.4


def map_components_to_tests(components: list[Component], tests: list[TestCase]) -> list[TestCase]:
    """Assign each test its best-matching component via naming-convention heuristics.

    Returns new TestCase objects (inputs are not mutated); tests below the
    confidence threshold are left unmapped rather than guessing, so
    downstream consumers can distinguish "no coverage found" from a weak match.
    """
    candidates = [c for c in components if c.kind in ("function", "method")]

    mapped: list[TestCase] = []
    for test in tests:
        best_id: str | None = None
        best_score = 0.0
        for comp in candidates:
            score = h.naming_convention_match(test.name, comp.name)
            if score > best_score:
                best_score, best_id = score, comp.id

        if best_id and best_score >= CONFIDENCE_THRESHOLD:
            mapped.append(
                test.model_copy(
                    update={
                        "target_component_ids": [best_id],
                        "mapping_method": "naming_convention",
                        "mapping_confidence": round(best_score, 2),
                    }
                )
            )
        else:
            mapped.append(
                test.model_copy(
                    update={
                        "target_component_ids": [],
                        "mapping_method": "unmapped",
                        "mapping_confidence": 0.0,
                    }
                )
            )
    return mapped
