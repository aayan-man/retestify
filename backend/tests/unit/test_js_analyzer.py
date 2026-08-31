from pathlib import Path

from app.analyzers.javascript.analyzer import JSAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_js_repo"


def test_parse_extracts_functions_and_class_methods():
    analyzer = JSAnalyzer()
    file_path = FIXTURE_ROOT / "calculator.js"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"add", "divide", "Calculator", "constructor"}.issubset(names)

    divide_comp = next(c for c in result.components if c.name == "divide")
    assert divide_comp.kind == "function"
    assert divide_comp.metrics.cyclomatic_complexity == 2  # base + 1 if-branch

    method = next(c for c in result.components if c.qualified_name == "Calculator.add")
    assert method.kind == "method"
    assert method.parent_id is not None


def test_list_test_cases_extracts_test_and_it_calls():
    analyzer = JSAnalyzer()
    file_path = FIXTURE_ROOT / "calculator.test.js"
    tests = analyzer.list_test_cases(file_path, project_id="proj_test", root=FIXTURE_ROOT, framework="jest")

    names = {t.name for t in tests}
    assert names == {"test_add_works", "test_divide_works", "test_divide_throws_on_zero"}
    assert all(t.language == "javascript" and t.framework == "jest" for t in tests)


def test_is_test_file_detection():
    analyzer = JSAnalyzer()
    assert analyzer.is_test_file(Path("calculator.test.js"))
    assert not analyzer.is_test_file(Path("calculator.js"))
