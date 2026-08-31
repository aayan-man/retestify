import shutil
from pathlib import Path

from app.ai_engine.schemas import GeneratedTest
from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore
from app.test_writer.python_writer import write_generated_test

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


def test_write_generated_test_appends_to_existing_test_file():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        components = JSONFileStore().load_components(workspace)
        divide_component = next(c for c in components if c.name == "divide")

        generated = GeneratedTest(
            test_name="test_divide_negative",
            code="def test_divide_negative():\n    assert divide(-6, 3) == -2",
            rationale="Covers a negative numerator.",
            confidence=0.8,
        )
        new_test = write_generated_test(workspace, divide_component, generated, "pytest")

        assert new_test.origin == "ai_generated"
        assert new_test.file_path == "tests/test_calculator.py"
        assert new_test.target_component_ids == [divide_component.id]

        written = (workspace.source_dir / "tests" / "test_calculator.py").read_text(encoding="utf-8")
        assert "test_divide_negative" in written
        # the new function's recorded line range must match where it actually landed
        lines = written.splitlines()
        assert "def test_divide_negative" in lines[new_test.line_start - 1]
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def test_write_generated_test_creates_new_file_when_none_exists():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        components = JSONFileStore().load_components(workspace)
        # Fabricate a component in a module with no existing test file
        no_test_component = next(c for c in components if c.name == "Calculator")

        generated = GeneratedTest(
            test_name="test_calculator_starts_at_zero",
            code="def test_calculator_starts_at_zero():\n    assert Calculator().value == 0",
            rationale="Covers default construction.",
            confidence=0.7,
        )
        # Calculator's module already has tests/test_calculator.py, so redirect
        # to a component whose module has none by editing file_path directly.
        fabricated = no_test_component.model_copy(update={"file_path": "utils/helpers.py"})

        new_test = write_generated_test(workspace, fabricated, generated, "pytest")

        assert new_test.file_path == "tests/test_helpers.py"
        assert (workspace.source_dir / "tests" / "test_helpers.py").exists()
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
