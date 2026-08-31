import shutil
from pathlib import Path

from app.jobs import pipeline

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_js_repo"


def test_ingest_and_analyze_sample_js_repo():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        summary = pipeline.analyze(workspace)

        assert "javascript" in summary.stack.languages
        assert "jest" in summary.stack.test_frameworks
        assert summary.parse_errors == []
        assert summary.component_count >= 4  # add, divide, Calculator, constructor, add(method)
        assert summary.test_count == 3
        assert summary.mapped_test_count >= 2  # test_add_works / test_divide_works should map cleanly
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
