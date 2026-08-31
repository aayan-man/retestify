from __future__ import annotations

import uuid

from app.knowledge_base.schema import ChangeRecord, Component, TestCase


def _key(c: Component) -> tuple[str, str]:
    """A component's id embeds its line number, which shifts whenever
    earlier code in the same file is edited — so identity for diffing has
    to be (file_path, qualified_name) instead."""
    return (c.file_path, c.qualified_name)


def detect_changes(
    project_id: str,
    old_components: list[Component],
    new_components: list[Component],
    old_tests: list[TestCase],
    from_commit: str | None,
    to_commit: str | None,
) -> list[ChangeRecord]:
    old_by_key = {_key(c): c for c in old_components}
    new_by_key = {_key(c): c for c in new_components}

    tests_by_old_component: dict[str, list[str]] = {}
    for t in old_tests:
        for cid in t.target_component_ids:
            tests_by_old_component.setdefault(cid, []).append(t.id)

    changes: list[ChangeRecord] = []

    for key, new_comp in new_by_key.items():
        old_comp = old_by_key.get(key)
        if old_comp is None:
            changes.append(
                ChangeRecord(
                    id=f"chg_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    from_commit=from_commit,
                    to_commit=to_commit,
                    component_id=new_comp.id,
                    change_type="added",
                    diff_summary=f"{new_comp.qualified_name} added",
                    new_content_hash=new_comp.content_hash,
                )
            )
        elif old_comp.content_hash != new_comp.content_hash:
            changes.append(
                ChangeRecord(
                    id=f"chg_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    from_commit=from_commit,
                    to_commit=to_commit,
                    component_id=new_comp.id,
                    change_type="modified",
                    diff_summary=(
                        f"{new_comp.qualified_name} changed "
                        f"({old_comp.metrics.loc} LOC -> {new_comp.metrics.loc} LOC)"
                    ),
                    old_content_hash=old_comp.content_hash,
                    new_content_hash=new_comp.content_hash,
                    affected_test_ids=tests_by_old_component.get(old_comp.id, []),
                )
            )

    for key, old_comp in old_by_key.items():
        if key not in new_by_key:
            changes.append(
                ChangeRecord(
                    id=f"chg_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    from_commit=from_commit,
                    to_commit=to_commit,
                    component_id=old_comp.id,
                    change_type="deleted",
                    diff_summary=f"{old_comp.qualified_name} deleted",
                    old_content_hash=old_comp.content_hash,
                    affected_test_ids=tests_by_old_component.get(old_comp.id, []),
                )
            )

    return changes
