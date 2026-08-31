import shutil
from pathlib import Path

import pytest

from app.jobs import pipeline

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.parametrize(
    "fixture_name,expected_language,expected_framework,min_components,expected_tests",
    [
        ("sample_java_repo", "java", "junit", 3, 1),
        ("sample_cpp_repo", "cpp", "gtest", 2, 1),
        ("sample_go_repo", "go", "testing", 3, 1),
        ("sample_csharp_repo", "csharp", "xunit", 2, 1),
    ],
)
def test_ingest_and_analyze_multi_language_fixture(
    fixture_name, expected_language, expected_framework, min_components, expected_tests
):
    fixture_root = FIXTURES_DIR / fixture_name
    workspace = pipeline.ingest_source(path=str(fixture_root))
    try:
        summary = pipeline.analyze(workspace)

        assert expected_language in summary.stack.languages
        assert expected_framework in summary.stack.test_frameworks
        assert summary.parse_errors == []
        assert summary.component_count >= min_components
        assert summary.test_count == expected_tests
        assert summary.mapped_test_count >= 1
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
