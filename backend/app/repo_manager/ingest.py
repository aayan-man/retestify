import shutil
import uuid
import zipfile
from pathlib import Path

import git

from app.config import settings

from .sandbox import safe_extract
from .workspace import Workspace, clean_name


def _new_workspace(name: str | None = None) -> Workspace:
    project_id = uuid.uuid4().hex[:12]
    root = settings.workspace_root / project_id
    ws = Workspace(project_id=project_id, root=root, name=clean_name(name))
    ws.ensure_dirs()
    ws.save_meta()
    return ws


def _repo_name_from_url(url: str) -> str | None:
    """Last path segment of a clone URL, minus any .git suffix. Works for
    https, ssh and local paths alike."""
    trimmed = url.rstrip("/").removesuffix(".git")
    segment = trimmed.replace("\\", "/").rsplit("/", 1)[-1]
    return segment.rsplit(":", 1)[-1] or None


def extract_zip(zip_path: str | Path) -> Workspace:
    ws = _new_workspace(Path(zip_path).stem)
    with zipfile.ZipFile(zip_path) as zf:
        safe_extract(zf, ws.source_dir)
    _flatten_single_root(ws.source_dir)
    return ws


def clone_github(url: str, ref: str | None = None) -> Workspace:
    ws = _new_workspace(_repo_name_from_url(url))
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
    ws = _new_workspace(Path(src_dir).name)
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
