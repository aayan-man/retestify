from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.test_analyzer.mapper import map_components_to_tests

_METRICS = ComponentMetrics(loc=3, cyclomatic_complexity=1, nesting_depth=0, num_params=2)


def _component(name: str, comp_id: str) -> Component:
    return Component(
        id=comp_id,
        project_id="proj_test",
        language="python",
        kind="function",
        name=name,
        qualified_name=f"calculator.{name}",
        file_path="calculator.py",
        line_start=1,
        line_end=3,
        metrics=_METRICS,
        content_hash="sha256:deadbeef",
    )


def _test_case(name: str, test_id: str) -> TestCase:
    return TestCase(
        id=test_id,
        project_id="proj_test",
        language="python",
        framework="pytest",
        name=name,
        file_path="tests/test_calculator.py",
        line_start=1,
        line_end=2,
        content_hash="sha256:cafebabe",
    )


def test_maps_test_to_matching_component_by_naming_convention():
    components = [_component("add", "c1"), _component("divide", "c2")]
    tests = [_test_case("test_divide", "t1")]

    mapped = map_components_to_tests(components, tests)

    assert mapped[0].target_component_ids == ["c2"]
    assert mapped[0].mapping_method == "naming_convention"
    assert mapped[0].mapping_confidence >= 0.7


def test_leaves_test_unmapped_below_confidence_threshold():
    components = [_component("add", "c1")]
    tests = [_test_case("test_something_unrelated_entirely", "t1")]

    mapped = map_components_to_tests(components, tests)

    assert mapped[0].target_component_ids == []
    assert mapped[0].mapping_method == "unmapped"
