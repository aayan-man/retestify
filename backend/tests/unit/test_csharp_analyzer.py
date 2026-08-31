from pathlib import Path

from app.analyzers.csharp.analyzer import CSharpAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_csharp_repo"


def test_parse_extracts_class_and_method():
    analyzer = CSharpAnalyzer()
    file_path = FIXTURE_ROOT / "Calculator.cs"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"Calculator", "Add"}.issubset(names)

    add_method = next(c for c in result.components if c.name == "Add")
    assert add_method.kind == "method"
    assert add_method.metrics.cyclomatic_complexity == 2
    assert add_method.qualified_name == "Calculator.Add"


def test_list_test_cases_detects_fact_attribute():
    analyzer = CSharpAnalyzer()
    file_path = FIXTURE_ROOT / "CalculatorTest.cs"
    tests = analyzer.list_test_cases(file_path, project_id="proj_test", root=FIXTURE_ROOT, framework="xunit")

    assert len(tests) == 1
    assert tests[0].name == "TestAdd"


def test_is_test_file_detection():
    analyzer = CSharpAnalyzer()
    assert analyzer.is_test_file(Path("CalculatorTest.cs"))
    assert not analyzer.is_test_file(Path("Calculator.cs"))
