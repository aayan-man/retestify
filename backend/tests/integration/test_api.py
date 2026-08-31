import io
import subprocess
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.jobs import pipeline
from app.main import app

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_python_repo"

client = TestClient(app)


def _zip_fixture_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in FIXTURE_ROOT.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(FIXTURE_ROOT))
    return buf.getvalue()


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_zip_analyzes_and_exposes_components_and_tests():
    resp = client.post(
        "/projects/upload",
        files={"file": ("sample.zip", _zip_fixture_bytes(), "application/zip")},
    )
    assert resp.status_code == 200
    summary = resp.json()
    project_id = summary["project_id"]
    try:
        assert summary["languages"] == ["python"]
        assert summary["component_count"] >= 5
        assert summary["test_count"] == 3

        components = client.get(f"/projects/{project_id}/components")
        assert components.status_code == 200
        assert len(components.json()) == summary["component_count"]

        tests = client.get(f"/projects/{project_id}/tests")
        assert tests.status_code == 200
        assert len(tests.json()) == 3
    finally:
        import shutil

        from app.repo_manager.workspace import load_workspace

        shutil.rmtree(load_workspace(project_id).root, ignore_errors=True)


def test_classify_endpoint_uses_configured_provider(monkeypatch):
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
                text="", raw_json={"decision": "retain", "rationale": "fine", "confidence": 0.7},
                model="fake-model", provider=self.name,
            )

        def count_tokens(self, text: str) -> int:
            return 1

    monkeypatch.setattr(pipeline, "get_provider", lambda name=None: FakeProvider())

    resp = client.post(
        "/projects/upload",
        files={"file": ("sample.zip", _zip_fixture_bytes(), "application/zip")},
    )
    project_id = resp.json()["project_id"]
    try:
        classify_resp = client.post(f"/projects/{project_id}/classify")
        assert classify_resp.status_code == 200
        recommendations = classify_resp.json()
        assert len(recommendations) > 0
        assert all(r["decision"] in ("retain", "modify", "remove", "generate") for r in recommendations)

        listed = client.get(f"/projects/{project_id}/recommendations")
        assert listed.status_code == 200
        assert len(listed.json()) == len(recommendations)

        report = client.get(f"/projects/{project_id}/report")
        assert report.status_code == 200
        assert report.json()["total_recommendations"] == len(recommendations)
    finally:
        import shutil

        from app.repo_manager.workspace import load_workspace

        shutil.rmtree(load_workspace(project_id).root, ignore_errors=True)


def test_unknown_project_returns_404():
    resp = client.get("/projects/does-not-exist/components")
    assert resp.status_code == 404


def test_webhook_push_event_triggers_incremental_analysis(tmp_path, monkeypatch):
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
                text="", raw_json={"decision": "retain", "rationale": "fine", "confidence": 0.7},
                model="fake-model", provider=self.name,
            )

        def count_tokens(self, text: str) -> int:
            return 1

    monkeypatch.setattr(pipeline, "get_provider", lambda name=None: FakeProvider())

    origin = tmp_path / "origin"
    origin.mkdir()
    _run_git(["init", "-q"], origin)
    _run_git(["config", "user.email", "test@example.com"], origin)
    _run_git(["config", "user.name", "Test"], origin)
    (origin / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _run_git(["add", "."], origin)
    _run_git(["commit", "-q", "-m", "initial"], origin)

    resp = client.post("/projects", json={"github_url": str(origin)})
    project_id = resp.json()["project_id"]
    try:
        (origin / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")
        _run_git(["add", "."], origin)
        _run_git(["commit", "-q", "-m", "trivial edit"], origin)

        webhook_resp = client.post(
            f"/webhooks/github/{project_id}",
            json={"ref": "refs/heads/main"},
            headers={"X-GitHub-Event": "push"},
        )
        assert webhook_resp.status_code == 200
        body = webhook_resp.json()
        assert body["status"] == "ok"
        assert body["changes"] == 1
        assert body["recommendations"] == 1
    finally:
        import shutil

        from app.repo_manager.workspace import load_workspace

        shutil.rmtree(load_workspace(project_id).root, ignore_errors=True)
