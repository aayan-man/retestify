from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# A display name is cosmetic, but it ends up in a page title and a filename,
# so it is kept short and stripped of anything that isn't printable.
MAX_NAME_LENGTH = 80


@dataclass
class Workspace:
    """A managed on-disk area for one ingested target repository."""

    project_id: str
    root: Path
    # What the project was called where it came from -- the uploaded zip's
    # name, the GitHub repo, or the directory. Falls back to the project_id
    # for workspaces ingested before names were recorded.
    name: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.project_id

    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def kb_dir(self) -> Path:
        return self.root / "kb"

    @property
    def meta_path(self) -> Path:
        return self.root / "meta.json"

    def ensure_dirs(self) -> None:
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.kb_dir.mkdir(parents=True, exist_ok=True)

    def save_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps({"project_id": self.project_id, "name": self.name}, indent=2),
            encoding="utf-8",
        )


def clean_name(raw: str | None) -> str | None:
    """Normalize a name taken from a filename, URL or directory.

    Returns None rather than an empty string so callers can fall back to the
    project_id with a plain `or`.
    """
    if not raw:
        return None
    cleaned = " ".join(str(raw).split())  # collapse whitespace, including newlines
    cleaned = "".join(ch for ch in cleaned if ch.isprintable()).strip(" .-_")
    return cleaned[:MAX_NAME_LENGTH] or None


def load_workspace(project_id: str) -> Workspace:
    from app.config import settings

    root = settings.workspace_root / project_id
    if not root.exists():
        raise FileNotFoundError(f"no workspace found for project_id {project_id!r}")

    name: str | None = None
    meta_path = root / "meta.json"
    if meta_path.is_file():
        try:
            name = clean_name(json.loads(meta_path.read_text(encoding="utf-8")).get("name"))
        except (OSError, json.JSONDecodeError):
            name = None  # a missing or corrupt name must never block loading
    return Workspace(project_id=project_id, root=root, name=name)
