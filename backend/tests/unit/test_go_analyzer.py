from pathlib import Path

from app.analyzers.go.analyzer import GoAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_go_repo"


def test_parse_extracts_function_struct_and_method():
    analyzer = GoAnalyzer()
    file_path = FIXTURE_ROOT / "calculator.go"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"Add", "Calculator", "Multiply"}.issubset(names)

    add_fn = next(c for c in result.components if c.name == "Add")
    assert add_fn.kind == "function"
    assert add_fn.metrics.cyclomatic_complexity == 2

    calculator = next(c for c in result.components if c.name == "Calculator")
    assert calculator.kind == "class"

    multiply = next(c for c in result.components if c.name == "Multiply")
    assert multiply.kind == "method"
    assert multiply.qualified_name == "Calculator.Multiply"
    assert multiply.parent_id == calculator.id


def test_list_test_cases_detects_test_prefixed_functions():
    analyzer = GoAnalyzer()
    file_path = FIXTURE_ROOT / "calculator_test.go"
    tests = analyzer.list_test_cases(file_path, project_id="proj_test", root=FIXTURE_ROOT, framework="testing")

    assert len(tests) == 1
    assert tests[0].name == "TestAdd"


def test_is_test_file_detection():
    analyzer = GoAnalyzer()
    assert analyzer.is_test_file(Path("calculator_test.go"))
    assert not analyzer.is_test_file(Path("calculator.go"))
