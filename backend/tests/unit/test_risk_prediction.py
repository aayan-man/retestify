from app.knowledge_base.schema import ChangeRecord, Component, ComponentMetrics
from app.risk_prediction.churn_risk import compute_churn_risks
from app.risk_prediction.pattern_detector import detect_code_smells


def _component(comp_id: str, name: str, kind="function", *, loc=10, complexity=1, nesting=0, params=1, parent_id=None) -> Component:
    return Component(
        id=comp_id,
        project_id="proj_test",
        language="python",
        kind=kind,
        name=name,
        qualified_name=name,
        file_path="mod.py",
        line_start=1,
        line_end=loc,
        parent_id=parent_id,
        metrics=ComponentMetrics(loc=loc, cyclomatic_complexity=complexity, nesting_depth=nesting, num_params=params),
        content_hash="sha256:deadbeef",
    )


def test_detects_god_method():
    comp = _component("py:mod.py:big_fn:1", "big_fn", loc=80, complexity=15)
    risks = detect_code_smells([comp], "proj_test")
    assert any(r.category == "god_method" for r in risks)


def test_detects_god_class_by_method_count():
    cls = _component("py:mod.py:Big:1", "Big", kind="class", loc=200)
    methods = [
        _component(f"py:mod.py:Big.m{i}:{i}", f"m{i}", kind="method", parent_id=cls.id) for i in range(12)
    ]
    risks = detect_code_smells([cls, *methods], "proj_test")
    assert any(r.category == "god_class" and r.evidence["method_count"] == 12 for r in risks)


def test_detects_long_parameter_list():
    comp = _component("py:mod.py:fn:1", "fn", params=6)
    risks = detect_code_smells([comp], "proj_test")
    assert any(r.category == "long_parameter_list" for r in risks)


def test_detects_deep_nesting():
    comp = _component("py:mod.py:fn:1", "fn", nesting=5)
    risks = detect_code_smells([comp], "proj_test")
    assert any(r.category == "deep_nesting" for r in risks)


def test_clean_component_has_no_smells():
    comp = _component("py:mod.py:add:1", "add", loc=3, complexity=1, nesting=0, params=2)
    assert detect_code_smells([comp], "proj_test") == []


def test_custom_thresholds_are_respected():
    comp = _component("py:mod.py:fn:1", "fn", loc=20, complexity=6)
    assert detect_code_smells([comp], "proj_test") == []  # below default thresholds
    risks = detect_code_smells([comp], "proj_test", god_method_loc=15, god_method_complexity=5)
    assert any(r.category == "god_method" for r in risks)


def _change(component_id: str, change_type="modified") -> ChangeRecord:
    return ChangeRecord(
        id=f"chg_{component_id}_{change_type}",
        project_id="proj_test",
        component_id=component_id,
        change_type=change_type,
    )


def test_high_churn_flagged_when_modified_repeatedly():
    comp = _component("py:mod.py:hot_fn:5", "hot_fn")
    # component id line number shifts across snapshots, key strips it
    changes = [
        _change("py:mod.py:hot_fn:1"),
        _change("py:mod.py:hot_fn:3"),
        _change("py:mod.py:hot_fn:5"),
    ]
    risks = compute_churn_risks(changes, [comp], "proj_test", high_churn_threshold=3)
    assert len(risks) == 1
    assert risks[0].component_id == comp.id
    assert risks[0].evidence["modification_count"] == 3


def test_low_churn_not_flagged():
    comp = _component("py:mod.py:fn:1", "fn")
    changes = [_change("py:mod.py:fn:1")]
    assert compute_churn_risks(changes, [comp], "proj_test", high_churn_threshold=3) == []


def test_churn_ignores_deleted_components():
    changes = [_change("py:mod.py:gone:1"), _change("py:mod.py:gone:2"), _change("py:mod.py:gone:3")]
    assert compute_churn_risks(changes, [], "proj_test", high_churn_threshold=3) == []
