import json
import zipfile

import pytest

from app.repo_manager import ingest
from app.repo_manager.workspace import Workspace, clean_name, load_workspace


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/benjaminp/six", "six"),
        ("https://github.com/benjaminp/six.git", "six"),
        ("https://github.com/owner/repo/", "repo"),
        ("git@github.com:owner/repo.git", "repo"),
        ("C:/projects/my-app", "my-app"),
    ],
)
def test_repo_name_is_taken_from_the_clone_url(url, expected):
    assert ingest._repo_name_from_url(url) == expected


def test_clean_name_normalizes_and_bounds():
    assert clean_name("  my   project \n") == "my project"
    assert clean_name("-_trimmed_-") == "trimmed"
    assert clean_name("x" * 200) == "x" * 80
    # Empty after cleaning must be None, so callers fall back to the id.
    assert clean_name("   ") is None
    assert clean_name(None) is None


def test_zip_upload_is_named_after_the_file(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "workspace_root", tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    project = tmp_path / "Bio-mini_pr.zip"
    with zipfile.ZipFile(project, "w") as z:
        z.writestr("app.py", "def f():\n    return 1\n")

    ws = ingest.extract_zip(project)

    assert ws.name == "Bio-mini_pr"
    assert ws.display_name == "Bio-mini_pr"


def test_name_survives_reloading_the_workspace(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "workspace_root", tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    source = tmp_path / "my-project"
    source.mkdir()
    (source / "a.py").write_text("x = 1\n", encoding="utf-8")

    created = ingest.import_directory(source)
    reloaded = load_workspace(created.project_id)

    assert reloaded.name == "my-project"
    assert json.loads(created.meta_path.read_text(encoding="utf-8"))["name"] == "my-project"


def test_workspace_without_meta_falls_back_to_the_id(tmp_path, monkeypatch):
    """Workspaces ingested before names were recorded must still load."""
    from app.config import settings

    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    (tmp_path / "old123").mkdir()

    ws = load_workspace("old123")

    assert ws.name is None
    assert ws.display_name == "old123"


def test_corrupt_meta_does_not_block_loading(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "meta.json").write_text("{not json", encoding="utf-8")

    assert load_workspace("proj").display_name == "proj"


def test_display_name_prefers_the_name(tmp_path):
    assert Workspace(project_id="abc123", root=tmp_path, name="Checkout").display_name == "Checkout"
    assert Workspace(project_id="abc123", root=tmp_path).display_name == "abc123"
