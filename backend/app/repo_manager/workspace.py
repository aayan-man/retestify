from dataclasses import dataclass
from pathlib import Path


@dataclass
class Workspace:
    """A managed on-disk area for one ingested target repository."""

    project_id: str
    root: Path

    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def kb_dir(self) -> Path:
        return self.root / "kb"

    def ensure_dirs(self) -> None:
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.kb_dir.mkdir(parents=True, exist_ok=True)


def load_workspace(project_id: str) -> Workspace:
    from app.config import settings

    root = settings.workspace_root / project_id
    if not root.exists():
        raise FileNotFoundError(f"no workspace found for project_id {project_id!r}")
    return Workspace(project_id=project_id, root=root)
