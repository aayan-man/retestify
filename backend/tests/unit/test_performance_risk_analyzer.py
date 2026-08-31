from app.knowledge_base.schema import Component, ComponentMetrics
from app.performance_testing.risk_analyzer import analyze_performance_risks


def _component(name: str, *, loc=10, complexity=1, nesting=0, calls=None) -> Component:
    return Component(
        id=f"py:mod.py:{name}:1",
        project_id="proj_test",
        language="python",
        kind="function",
        name=name,
        qualified_name=f"mod.{name}",
        file_path="mod.py",
        line_start=1,
        line_end=loc,
        calls=calls or [],
        metrics=ComponentMetrics(loc=loc, cyclomatic_complexity=complexity, nesting_depth=nesting, num_params=1),
        content_hash="sha256:deadbeef",
    )


def test_flags_nested_loops_with_complexity():
    comp = _component("search", loc=20, complexity=5, nesting=2)
    risks = analyze_performance_risks([comp], "proj_test")
    assert any(r.category == "nested_loops" for r in risks)


def test_does_not_flag_simple_shallow_function():
    comp = _component("add", loc=3, complexity=1, nesting=0)
    risks = analyze_performance_risks([comp], "proj_test")
    assert risks == []


def test_flags_high_complexity_hot_path():
    comp = _component("dispatch", loc=80, complexity=20, nesting=0)
    risks = analyze_performance_risks([comp], "proj_test")
    assert any(r.category == "high_complexity_hot_path" for r in risks)


def test_flags_self_recursive_function():
    comp = _component("factorial", loc=5, complexity=2, calls=["factorial"])
    risks = analyze_performance_risks([comp], "proj_test")
    assert any(r.category == "unbounded_recursion" for r in risks)


def test_ignores_classes():
    cls = _component("Widget", loc=100, complexity=1, nesting=0)
    cls = cls.model_copy(update={"kind": "class"})
    risks = analyze_performance_risks([cls], "proj_test")
    assert risks == []
