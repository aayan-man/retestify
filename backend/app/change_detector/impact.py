from __future__ import annotations

from app.knowledge_base.schema import ChangeRecord, Component


def propagate_impact(changes: list[ChangeRecord], components: list[Component]) -> list[ChangeRecord]:
    """Heuristic impact analysis: flag any component whose `calls` list
    references the name of a changed component. This is a name-based
    approximation of a call graph, not full resolution — good enough as a
    signal for what else might be worth reclassifying, not a guarantee."""
    id_to_component = {c.id: c for c in components}

    updated: list[ChangeRecord] = []
    for change in changes:
        changed_comp = id_to_component.get(change.component_id)
        callers = (
            [c.id for c in components if c.id != change.component_id and changed_comp and changed_comp.name in c.calls]
            if changed_comp
            else []
        )
        updated.append(change.model_copy(update={"impact_propagated_to": callers}))
    return updated


def affected_component_ids(changes: list[ChangeRecord]) -> set[str]:
    """Components that need reclassification: everything directly changed
    (except deletions, which have no component left to classify) plus
    everything flagged as impacted by one of those changes."""
    ids: set[str] = set()
    for change in changes:
        if change.change_type != "deleted":
            ids.add(change.component_id)
        ids.update(change.impact_propagated_to)
    return ids
