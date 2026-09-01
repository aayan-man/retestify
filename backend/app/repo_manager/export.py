from __future__ import annotations

import io
import zipfile

from app.repo_manager.workspace import Workspace

_EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", "target", "bin", "obj",
}


def build_zip_bytes(workspace: Workspace) -> bytes:
    """Re-zip the workspace's current source tree (including any
    AI-generated test files written into it) so the modified project can be
    downloaded back out — the workspace itself is server-side only and
    never otherwise leaves the machine running the backend."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in workspace.source_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _EXCLUDED_DIRS for part in path.relative_to(workspace.source_dir).parts):
                continue
            zf.write(path, path.relative_to(workspace.source_dir))
    return buf.getvalue()
