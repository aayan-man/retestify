import shutil
from pathlib import Path

from app.ai_engine.schemas import GeneratedTest
from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore
from app.test_writer.common import insert_method_into_class
from app.test_writer.csharp_writer import write_generated_test as write_csharp_test
from app.test_writer.java_writer import write_generated_test as write_java_test

JAVA_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_java_repo"
CSHARP_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_csharp_repo"


def test_insert_method_into_class_creates_new_file(tmp_path):
    test_file = tmp_path / "FooTest.java"
    start, end = insert_method_into_class(
        test_file, "@Test\npublic void testBar() {\n    assertTrue(true);\n}", "public class FooTest {\n"
    )
    content = test_file.read_text(encoding="utf-8")
    assert content.startswith("public class FooTest {\n")
    assert content.rstrip().endswith("}")
    assert content.count("{") == content.count("}")
    lines = content.splitlines()
    assert any("testBar" in line for line in lines[start - 1 : end])


def test_insert_method_into_class_appends_before_closing_brace(tmp_path):
    test_file = tmp_path / "FooTest.java"
    test_file.write_text(
        "public class FooTest {\n    @Test\n    public void testExisting() {\n        assertTrue(true);\n    }\n}\n",
        encoding="utf-8",
    )
    start, end = insert_method_into_class(test_file, "@Test\npublic void testNew() {\n    assertTrue(false);\n}", "unused")

    content = test_file.read_text(encoding="utf-8")
    assert "testExisting" in content
    assert "testNew" in content
    assert content.count("{") == content.count("}")
    lines = content.splitlines()
    assert any("testNew" in line for line in lines[start - 1 : end])
    # the new method must land before the class's final closing brace
    assert content.index("testNew") < content.rindex("}")


def test_java_writer_creates_valid_new_test_class():
    workspace = pipeline.ingest_source(path=str(JAVA_FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        components = JSONFileStore().load_components(workspace)
        divide_component = next(c for c in components if c.name == "divide")

        generated = GeneratedTest(
            test_name="testDivideByZeroThrows",
            code="public void testDivideByZeroThrows() {\n    assertThrows(IllegalArgumentException.class, () -> new Calculator().divide(1, 0));\n}",
            rationale="Covers the error path.",
            confidence=0.8,
        )
        new_test = write_java_test(workspace, divide_component, generated, "junit")

        written = (workspace.source_dir / new_test.file_path).read_text(encoding="utf-8")
        assert written.count("{") == written.count("}")
        assert "testDivideByZeroThrows" in written
        assert "@Test" in written
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def test_csharp_writer_auto_adds_fact_attribute():
    workspace = pipeline.ingest_source(path=str(CSHARP_FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        components = JSONFileStore().load_components(workspace)
        add_component = next(c for c in components if c.name == "Add")

        generated = GeneratedTest(
            test_name="TestAddNegative",
            code="public void TestAddNegative()\n{\n    Assert.Equal(-1, new Calculator().Add(-5, 3));\n}",
            rationale="Covers the negative-input branch.",
            confidence=0.75,
        )
        new_test = write_csharp_test(workspace, add_component, generated, "xunit")

        written = (workspace.source_dir / new_test.file_path).read_text(encoding="utf-8")
        assert written.count("{") == written.count("}")
        assert "[Fact]" in written
        assert "TestAddNegative" in written
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
