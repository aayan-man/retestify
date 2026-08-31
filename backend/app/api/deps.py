from fastapi import HTTPException

from app.repo_manager.workspace import Workspace, load_workspace


def get_workspace_or_404(project_id: str) -> Workspace:
    try:
        return load_workspace(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"no project found for id {project_id!r}")
