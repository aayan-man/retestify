import shutil
from pathlib import Path

from app.ai_engine.decision_engine import classify_project
from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, canned: dict):
        self.canned = canned

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema=None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return LLMResponse(text="", raw_json=self.canned, model="fake-model", provider=self.name)

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def test_classify_project_retains_well_matched_tests_and_flags_uncovered_methods():
    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        store = JSONFileStore()
        components = store.load_components(workspace)
        tests = store.load_tests(workspace)

        provider = FakeProvider(
            {"decision": "retain", "rationale": "Covers the happy path and the error case.", "confidence": 0.88}
        )
        recommendations = classify_project(workspace, provider, components, tests)

        add_rec = next(r for r in recommendations if r.component_id.endswith(":add:1"))
        assert add_rec.decision == "retain"
        assert add_rec.confidence == 0.88
        assert add_rec.related_test_ids

        # Calculator.add(self, n) is a method with no mapped test -> "generate", no LLM call needed
        method_rec = next(r for r in recommendations if "Calculator.add" in r.component_id)
        assert method_rec.decision == "generate"
        assert method_rec.related_test_ids == []
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
