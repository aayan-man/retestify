import shutil
import uuid
import zipfile
from pathlib import Path

import git

from app.config import settings

from .sandbox import safe_extract
from .workspace import Workspace


def _new_workspace() -> Workspace:
    project_id = uuid.uuid4().hex[:12]
    root = settings.workspace_root / project_id
    ws = Workspace(project_id=project_id, root=root)
    ws.ensure_dirs()
    return ws


def extract_zip(zip_path: str | Path) -> Workspace:
    ws = _new_workspace()
    with zipfile.ZipFile(zip_path) as zf:
        safe_extract(zf, ws.source_dir)
    _flatten_single_root(ws.source_dir)
    return ws


def clone_github(url: str, ref: str | None = None) -> Workspace:
    ws = _new_workspace()
    if ref:
        git.Repo.clone_from(url, ws.source_dir, depth=1, branch=ref)
    else:
        git.Repo.clone_from(url, ws.source_dir, depth=1)
    return ws


def import_directory(src_dir: Path) -> Workspace:
    """Copy an already-local directory into a managed workspace.

    Lets the CLI point at a directory on disk during development without
    round-tripping it through a zip file first.
    """
    ws = _new_workspace()
    shutil.copytree(
        src_dir,
        ws.source_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git"),
    )
    return ws


def _flatten_single_root(source_dir: Path) -> None:
    """GitHub zip exports wrap the repo in a single top-level folder; unwrap it."""
    entries = list(source_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for item in inner.iterdir():
            shutil.move(str(item), str(source_dir / item.name))
        inner.rmdir()
