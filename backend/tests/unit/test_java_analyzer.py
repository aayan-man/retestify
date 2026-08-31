from pathlib import Path

from app.analyzers.java.analyzer import JavaAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_java_repo"


def test_parse_extracts_class_and_methods():
    analyzer = JavaAnalyzer()
    file_path = FIXTURE_ROOT / "src" / "main" / "java" / "Calculator.java"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"Calculator", "add", "divide"}.issubset(names)

    add_method = next(c for c in result.components if c.name == "add")
    assert add_method.kind == "method"
    assert add_method.metrics.cyclomatic_complexity == 2  # base + 1 if-branch
    assert add_method.parent_id is not None
    assert add_method.qualified_name == "Calculator.add"


def test_list_test_cases_detects_junit_test_annotation():
    analyzer = JavaAnalyzer()
    file_path = FIXTURE_ROOT / "src" / "test" / "java" / "CalculatorTest.java"
    tests = analyzer.list_test_cases(file_path, project_id="proj_test", root=FIXTURE_ROOT, framework="junit")

    assert len(tests) == 1
    assert tests[0].name == "testAdd"
    assert tests[0].language == "java"


def test_is_test_file_detection():
    analyzer = JavaAnalyzer()
    assert analyzer.is_test_file(Path("src/test/java/CalculatorTest.java"))
    assert not analyzer.is_test_file(Path("src/main/java/Calculator.java"))
