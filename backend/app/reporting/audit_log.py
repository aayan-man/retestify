from __future__ import annotations

import json
from datetime import datetime, timezone

from app.knowledge_base.paths import audit_log_path
from app.repo_manager.workspace import Workspace


def log_event(workspace: Workspace, event_type: str, **fields) -> None:
    """Append one JSONL entry recording an AI decision or test-file
    modification, so every recommendation and write is auditable."""
    entry = {
        "event_type": event_type,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    path = audit_log_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_events(workspace: Workspace) -> list[dict]:
    path = audit_log_path(workspace)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
