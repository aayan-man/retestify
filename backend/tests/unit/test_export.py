import zipfile
from io import BytesIO
from pathlib import Path

from app.repo_manager.export import build_zip_bytes
from app.repo_manager.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()
    return ws


def test_build_zip_includes_source_and_generated_tests(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws.source_dir / "tests").mkdir()
    (ws.source_dir / "tests" / "test_calc.py").write_text("def test_add():\n    pass\n", encoding="utf-8")

    zip_bytes = build_zip_bytes(ws)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    assert "calc.py" in names
    assert "tests/test_calc.py" in names


def test_build_zip_excludes_git_and_cache_dirs(tmp_path):
    ws = _workspace(tmp_path)
    (ws.source_dir / "calc.py").write_text("x = 1\n", encoding="utf-8")
    (ws.source_dir / ".git").mkdir()
    (ws.source_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (ws.source_dir / "__pycache__").mkdir()
    (ws.source_dir / "__pycache__" / "calc.cpython-313.pyc").write_bytes(b"\x00")

    zip_bytes = build_zip_bytes(ws)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    assert "calc.py" in names
    assert not any(".git" in n for n in names)
    assert not any("__pycache__" in n for n in names)
