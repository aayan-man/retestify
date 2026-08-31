from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.repo_manager.workspace import Workspace

from . import paths as kb_paths
from .schema import ChangeRecord, Component, Recommendation, TestCase

T = TypeVar("T", bound=BaseModel)
SCHEMA_VERSION = 1


class KnowledgeBaseStore(ABC):
    """Contract for persisting/loading the four knowledge-base collections.

    JSONFileStore is the only implementation for now; a SQLiteStore can be
    added later behind this same interface without touching callers.
    """

    @abstractmethod
    def save_components(self, ws: Workspace, items: list[Component]) -> None: ...

    @abstractmethod
    def load_components(self, ws: Workspace) -> list[Component]: ...

    @abstractmethod
    def save_tests(self, ws: Workspace, items: list[TestCase]) -> None: ...

    @abstractmethod
    def load_tests(self, ws: Workspace) -> list[TestCase]: ...

    @abstractmethod
    def save_changes(self, ws: Workspace, items: list[ChangeRecord]) -> None: ...

    @abstractmethod
    def load_changes(self, ws: Workspace) -> list[ChangeRecord]: ...

    @abstractmethod
    def save_recommendations(self, ws: Workspace, items: list[Recommendation]) -> None: ...

    @abstractmethod
    def load_recommendations(self, ws: Workspace) -> list[Recommendation]: ...


def _write_collection(path: Path, project_id: str, items: list[BaseModel]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump(mode="json") for item in items],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_collection(path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [model.model_validate(item) for item in data.get("items", [])]


class JSONFileStore(KnowledgeBaseStore):
    def save_components(self, ws: Workspace, items: list[Component]) -> None:
        _write_collection(kb_paths.components_path(ws), ws.project_id, items)

    def load_components(self, ws: Workspace) -> list[Component]:
        return _read_collection(kb_paths.components_path(ws), Component)

    def save_tests(self, ws: Workspace, items: list[TestCase]) -> None:
        _write_collection(kb_paths.tests_path(ws), ws.project_id, items)

    def load_tests(self, ws: Workspace) -> list[TestCase]:
        return _read_collection(kb_paths.tests_path(ws), TestCase)

    def save_changes(self, ws: Workspace, items: list[ChangeRecord]) -> None:
        _write_collection(kb_paths.changes_path(ws), ws.project_id, items)

    def load_changes(self, ws: Workspace) -> list[ChangeRecord]:
        return _read_collection(kb_paths.changes_path(ws), ChangeRecord)

    def save_recommendations(self, ws: Workspace, items: list[Recommendation]) -> None:
        _write_collection(kb_paths.recommendations_path(ws), ws.project_id, items)

    def load_recommendations(self, ws: Workspace) -> list[Recommendation]:
        return _read_collection(kb_paths.recommendations_path(ws), Recommendation)
