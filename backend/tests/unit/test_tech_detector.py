from app.repo_manager.workspace import Workspace
from app.tech_detector.detector import detect_stack


def _workspace(tmp_path) -> Workspace:
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()
    return ws


def test_bare_assert_functions_default_to_pytest_not_unittest(tmp_path):
    """A repo with plain `def test_*():` functions and no `import pytest`
    (pytest doesn't require importing itself to run) and no
    unittest.TestCase must be detected as pytest, not unittest — a bare
    function has no `self`, so treating it as unittest breaks generation
    (the AI Review Engine would ask for unittest-style code that can't run
    as a standalone function)."""
    ws = _workspace(tmp_path)
    (ws.source_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws.source_dir / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
    )

    stack = detect_stack(ws)

    assert "python" in stack.languages
    assert "pytest" in stack.test_frameworks
    assert "unittest" not in stack.test_frameworks


def test_unittest_testcase_subclass_detected_as_unittest(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws.source_dir / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )

    stack = detect_stack(ws)

    assert "unittest" in stack.test_frameworks
    assert "pytest" not in stack.test_frameworks


def test_explicit_pytest_import_detected_as_pytest(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "test_calc.py").write_text("import pytest\n\ndef test_x():\n    pass\n", encoding="utf-8")

    stack = detect_stack(ws)

    assert "pytest" in stack.test_frameworks
