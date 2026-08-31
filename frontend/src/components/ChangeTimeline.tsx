import type { ChangeRecord } from "../types/kb";

export function ChangeTimeline({ changes }: { changes: ChangeRecord[] }) {
  if (changes.length === 0) {
    return <p className="muted">No changes detected yet.</p>;
  }
  return (
    <ul className="change-timeline">
      {changes.map((c) => (
        <li key={c.id} className={`change-item change-${c.change_type}`}>
          <span className="change-type">{c.change_type}</span>
          <span className="change-summary">{c.diff_summary ?? c.component_id}</span>
          {c.impact_propagated_to.length > 0 && (
            <span className="change-impact">+{c.impact_propagated_to.length} impacted</span>
          )}
        </li>
      ))}
    </ul>
  );
}
