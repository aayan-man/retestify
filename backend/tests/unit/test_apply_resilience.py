import shutil
from pathlib import Path

from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.jobs import pipeline
from app.knowledge_base.store import JSONFileStore

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"


class _Provider(LLMProvider):
    """Classifies everything as "generate", then fails the first generation
    and returns usable code for the rest."""

    name = "fake"

    def __init__(self):
        self.generations = 0

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema=None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        schema_name = getattr(response_schema, "__name__", "")
        if schema_name == "TestClassification":
            payload = {"decision": "remove", "rationale": "no", "confidence": 0.5}
        else:
            self.generations += 1
            # The first component always comes back unparseable, however
            # many corrective retries it is given.
            code = "def broken(:" if self.generations <= 2 else "def test_ok():\n    assert True\n"
            payload = {"test_name": "test_ok", "code": code, "rationale": "r", "confidence": 0.9}
        return LLMResponse(text="", raw_json=payload, model="fake-model", provider=self.name)

    def count_tokens(self, text: str) -> int:
        return 1


class _WorkingProvider(_Provider):
    """Always returns usable code, so every actionable recommendation applies."""

    def complete(self, messages, *, system=None, response_schema=None, max_tokens=2048, temperature=0.2):
        schema_name = getattr(response_schema, "__name__", "")
        if schema_name == "TestClassification":
            payload = {"decision": "remove", "rationale": "no", "confidence": 0.5}
        else:
            payload = {
                "test_name": "test_ok",
                "code": "def test_ok():\n    assert True\n",
                "rationale": "r",
                "confidence": 0.9,
            }
        return LLMResponse(text="", raw_json=payload, model="fake-model", provider=self.name)


def test_apply_reports_progress_so_a_background_job_can_show_it(monkeypatch):
    """The dashboard polls a job for processed/total while applying runs, so
    the pipeline has to report both, counting only actionable work."""
    monkeypatch.setattr(pipeline, "require_provider", lambda name=None: _WorkingProvider())

    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        recommendations = pipeline.classify_project(workspace.project_id)
        actionable = sum(
            1 for r in recommendations if r.decision in ("generate", "modify") and r.status == "pending_review"
        )
        assert actionable > 0, "fixture should produce work to apply"

        seen: list[tuple[int, int]] = []
        pipeline.apply_recommendations(workspace.project_id, progress=lambda p, t: seen.append((p, t)))

        assert seen[0] == (0, actionable), "should report the total up front, before any slow work"
        assert seen[-1] == (actionable, actionable)
        # Monotonic, one step per actionable recommendation.
        assert [p for p, _ in seen] == list(range(0, actionable + 1))
        assert {t for _, t in seen} == {actionable}
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def test_one_unusable_generation_does_not_discard_the_rest_of_the_run(monkeypatch):
    """Applying is a long, paid-for loop that only persists at the end, so a
    single component the model can't write a test for must be recorded and
    skipped rather than aborting everything generated so far."""
    provider = _Provider()
    monkeypatch.setattr(pipeline, "require_provider", lambda name=None: provider)

    workspace = pipeline.ingest_source(path=str(FIXTURE_ROOT))
    try:
        pipeline.analyze(workspace)
        pipeline.classify_project(workspace.project_id)

        recommendations = pipeline.apply_recommendations(workspace.project_id)

        by_status: dict[str, int] = {}
        for rec in recommendations:
            by_status[rec.status] = by_status.get(rec.status, 0) + 1

        assert by_status.get("failed") == 1, "the unusable generation should be recorded as failed"
        assert by_status.get("applied", 0) >= 1, "later components should still have been written"

        failed = next(r for r in recommendations if r.status == "failed")
        assert failed.failure_reason and "valid" in failed.failure_reason

        # Progress must actually be persisted, not just returned.
        stored = JSONFileStore().load_recommendations(workspace)
        assert {r.status for r in stored} == {r.status for r in recommendations}
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
