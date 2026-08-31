from pathlib import Path

from app.analyzers.cpp.analyzer import CppAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_cpp_repo"


def test_parse_extracts_function_and_class_method():
    analyzer = CppAnalyzer()
    file_path = FIXTURE_ROOT / "calculator.cpp"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"add", "Calculator", "multiply"}.issubset(names)

    add_fn = next(c for c in result.components if c.name == "add")
    assert add_fn.kind == "function"
    assert add_fn.metrics.cyclomatic_complexity == 2

    multiply_method = next(c for c in result.components if c.name == "multiply")
    assert multiply_method.kind == "method"
    assert multiply_method.parent_id is not None
    assert multiply_method.qualified_name == "Calculator::multiply"


def test_list_test_cases_detects_gtest_macro():
    analyzer = CppAnalyzer()
    file_path = FIXTURE_ROOT / "calculator_test.cpp"
    tests = analyzer.list_test_cases(file_path, project_id="proj_test", root=FIXTURE_ROOT, framework="gtest")

    assert len(tests) == 1
    assert tests[0].name == "test_CalculatorTest_AddWorks"


def test_is_test_file_detection():
    analyzer = CppAnalyzer()
    assert analyzer.is_test_file(Path("calculator_test.cpp"))
    assert not analyzer.is_test_file(Path("calculator.cpp"))
