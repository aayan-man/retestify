import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_assess_risks_endpoint_and_listing_endpoints():
    resp = client.post(
        "/projects/upload",
        files={"file": ("sample.zip", _zip_fixture_bytes(), "application/zip")},
    )
    project_id = resp.json()["project_id"]
    try:
        assess_resp = client.post(f"/projects/{project_id}/assess-risks")
        assert assess_resp.status_code == 200
        body = assess_resp.json()
        assert set(body.keys()) == {"deployment_issues", "performance_risks", "predicted_risks"}

        assert client.get(f"/projects/{project_id}/deployment-issues").status_code == 200
        assert client.get(f"/projects/{project_id}/performance-risks").status_code == 200
        assert client.get(f"/projects/{project_id}/predicted-risks").status_code == 200
    finally:
        import shutil

        from app.repo_manager.workspace import load_workspace

        shutil.rmtree(load_workspace(project_id).root, ignore_errors=True)


def test_company_profile_endpoints():
    get_resp = client.get("/companies/example-corp")
    assert get_resp.status_code == 200
    assert get_resp.json()["company_id"] == "example-corp"

    list_resp = client.get("/companies")
    assert list_resp.status_code == 200
    assert any(c["company_id"] == "example-corp" for c in list_resp.json())

    missing_resp = client.get("/companies/does-not-exist")
    assert missing_resp.status_code == 404


def test_company_profile_upsert():
    payload = {"company_id": "test-co", "display_name": "Test Co", "style_guide": "Be concise."}
    put_resp = client.put("/companies/test-co", json=payload)
    assert put_resp.status_code == 200

    get_resp = client.get("/companies/test-co")
    assert get_resp.status_code == 200
    assert get_resp.json()["style_guide"] == "Be concise."

    from app.personalization.profile import _profiles_dir

    (_profiles_dir() / "test-co.json").unlink(missing_ok=True)
