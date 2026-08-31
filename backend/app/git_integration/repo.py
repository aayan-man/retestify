from __future__ import annotations

from datetime import datetime

import git

from app.repo_manager.workspace import Workspace


class NotAGitRepoError(Exception):
    pass


def is_git_repo(workspace: Workspace) -> bool:
    return (workspace.source_dir / ".git").exists()


def _repo(workspace: Workspace) -> git.Repo:
    if not is_git_repo(workspace):
        raise NotAGitRepoError(
            f"workspace {workspace.project_id!r} was not ingested via a GitHub URL, "
            "so it has no git history to track."
        )
    return git.Repo(workspace.source_dir)


def current_commit(workspace: Workspace) -> str:
    return _repo(workspace).head.commit.hexsha


def pull_latest(workspace: Workspace) -> str:
    """Fetch and merge new commits from origin, returning the new HEAD sha."""
    repo = _repo(workspace)
    repo.remotes.origin.pull()
    return repo.head.commit.hexsha


def list_commits(workspace: Workspace, max_count: int = 20) -> list[dict]:
    repo = _repo(workspace)
    return [
        {
            "sha": c.hexsha,
            "message": c.message.strip(),
            "author": c.author.name,
            "committed_at": datetime.fromtimestamp(c.committed_date).isoformat(),
        }
        for c in repo.iter_commits(max_count=max_count)
    ]
