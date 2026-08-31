import shutil
import subprocess
from pathlib import Path

from app.change_detector.impact import affected_component_ids
from app.jobs import pipeline


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_local_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    _run_git(["init", "-q"], origin)
    _run_git(["config", "user.email", "test@example.com"], origin)
    _run_git(["config", "user.name", "Test"], origin)
    (origin / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _run_git(["add", "."], origin)
    _run_git(["commit", "-q", "-m", "initial"], origin)
    return origin


def test_detect_changes_flags_modified_component_and_impacted_caller(tmp_path):
    origin = _init_local_repo(tmp_path)
    workspace = pipeline.ingest_source(github_url=str(origin))
    try:
        pipeline.analyze(workspace)

        # A second component that calls `add`, so we can verify impact propagation.
        (origin / "calc.py").write_text(
            "def add(a, b):\n"
            "    if a < 0:\n"
            "        raise ValueError('negative')\n"
            "    return a + b\n"
            "\n"
            "def add_twice(a, b):\n"
            "    return add(a, b) + add(a, b)\n",
            encoding="utf-8",
        )
        _run_git(["add", "."], origin)
        _run_git(["commit", "-q", "-m", "add validation and a caller"], origin)

        changes = pipeline.detect_changes(workspace.project_id)

        modified = [c for c in changes if c.change_type == "modified"]
        added = [c for c in changes if c.change_type == "added"]
        assert len(modified) == 1
        assert "add" in modified[0].component_id
        assert modified[0].from_commit is not None
        assert modified[0].to_commit is not None
        assert len(added) == 1  # add_twice

        affected = affected_component_ids(changes)
        assert modified[0].component_id in affected
        # add_twice calls add, so it should be flagged as impacted
        assert modified[0].impact_propagated_to
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def test_classify_changed_components_only_touches_affected_ids(tmp_path, monkeypatch):
    from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse

    class FakeProvider(LLMProvider):
        name = "fake"

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
                text="", raw_json={"decision": "retain", "rationale": "ok", "confidence": 0.9},
                model="fake-model", provider=self.name,
            )

        def count_tokens(self, text: str) -> int:
            return 1

    monkeypatch.setattr(pipeline, "get_provider", lambda name=None: FakeProvider())

    origin = _init_local_repo(tmp_path)
    workspace = pipeline.ingest_source(github_url=str(origin))
    try:
        pipeline.analyze(workspace)
        (origin / "calc.py").write_text(
            "def add(a, b):\n    return a + b + 0\n", encoding="utf-8"
        )
        _run_git(["add", "."], origin)
        _run_git(["commit", "-q", "-m", "trivial edit"], origin)
        pipeline.detect_changes(workspace.project_id)

        recommendations = pipeline.classify_changed_components(workspace.project_id)
        assert len(recommendations) == 1
        assert recommendations[0].component_id.split(":")[1] == "calc.py"
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)
