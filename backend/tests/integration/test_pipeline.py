from pathlib import Path

from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


def test_ingest_and_analyze_sample_repo():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        summary = pipeline.analyze(workspace)

        assert "python" in summary.stack.languages
        assert summary.parse_errors == []
        assert summary.component_count >= 5  # add, divide, Calculator, __init__, add(method)
        assert summary.test_count == 3
        assert summary.mapped_test_count >= 2  # test_add / test_divide should map cleanly

        store = JSONFileStore()
        components = store.load_components(workspace)
        tests = store.load_tests(workspace)
        assert len(components) == summary.component_count
        assert len(tests) == summary.test_count
    finally:
        import shutil

        shutil.rmtree(workspace.root, ignore_errors=True)
