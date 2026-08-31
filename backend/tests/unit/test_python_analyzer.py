from pathlib import Path

from app.analyzers.python.analyzer import PythonAnalyzer

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


def test_parse_extracts_functions_and_class_methods():
    analyzer = PythonAnalyzer()
    file_path = FIXTURE_ROOT / "calculator.py"
    result = analyzer.parse(file_path, project_id="proj_test", root=FIXTURE_ROOT)

    assert result.parse_errors == []
    names = {c.name for c in result.components}
    assert {"add", "divide", "Calculator", "__init__"}.issubset(names)

    divide_comp = next(c for c in result.components if c.name == "divide")
    assert divide_comp.kind == "function"
    assert divide_comp.metrics.cyclomatic_complexity == 2  # base + 1 if-branch

    calculator_init = next(
        c for c in result.components if c.name == "__init__" and c.kind == "method"
    )
    assert calculator_init.parent_id is not None


def test_is_test_file_detection():
    analyzer = PythonAnalyzer()
    assert analyzer.is_test_file(Path("tests/test_calculator.py"))
    assert not analyzer.is_test_file(Path("calculator.py"))
