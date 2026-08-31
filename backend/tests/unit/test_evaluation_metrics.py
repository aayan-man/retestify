import sys
from pathlib import Path

# research/ lives outside backend/'s package root; add the repo root so
# `research.evaluation.*` is importable when running the backend's own suite.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research.evaluation.cost_tracking import CostTrackingProvider  # noqa: E402
from research.evaluation.metrics import compute_accuracy, coverage_delta, summarize_decisions  # noqa: E402

from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse  # noqa: E402
from app.knowledge_base.schema import Recommendation  # noqa: E402


class _FixedProvider(LLMProvider):
    name = "fixed"

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema=None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return LLMResponse(
            text="ok", raw_json=None, model="fixed-model", provider=self.name,
            input_tokens=100, output_tokens=50, latency_ms=10,
        )

    def count_tokens(self, text: str) -> int:
        return len(text)


def _rec(component_id: str, decision: str) -> Recommendation:
    return Recommendation(
        id=f"rec_{component_id}",
        project_id="proj_test",
        component_id=component_id,
        decision=decision,
        rationale="r",
        confidence=0.5,
    )


def test_cost_tracking_provider_accumulates_across_calls():
    tracked = CostTrackingProvider(_FixedProvider())
    tracked.complete([{"role": "user", "content": "hi"}])
    tracked.complete([{"role": "user", "content": "hi again"}])

    assert tracked.call_count == 2
    assert tracked.total_input_tokens == 200
    assert tracked.total_output_tokens == 100


def test_coverage_delta():
    assert coverage_delta(50.0, 75.0) == 25.0
    assert coverage_delta(None, 75.0) is None


def test_summarize_decisions():
    recs = [_rec("c1", "retain"), _rec("c2", "retain"), _rec("c3", "generate")]
    assert summarize_decisions(recs) == {"retain": 2, "generate": 1}


def test_compute_accuracy_against_ground_truth():
    recs = [_rec("c1", "retain"), _rec("c2", "modify"), _rec("c3", "generate")]
    ground_truth = {"c1": "retain", "c2": "remove"}  # c2 disagrees, c3 unlabeled
    assert compute_accuracy(recs, ground_truth) == 0.5


def test_compute_accuracy_returns_none_without_ground_truth():
    recs = [_rec("c1", "retain")]
    assert compute_accuracy(recs, {}) is None
