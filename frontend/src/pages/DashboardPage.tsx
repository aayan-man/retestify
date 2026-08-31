import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ChangeTimeline } from "../components/ChangeTimeline";
import { RecommendationCard } from "../components/RecommendationCard";
import { RecommendationDetailPage } from "./RecommendationDetailPage";
import type { ChangeRecord, ProjectReport, ProjectSummary, Recommendation } from "../types/kb";

interface Props {
  summary: ProjectSummary;
}

export function DashboardPage({ summary }: Props) {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [changes, setChanges] = useState<ChangeRecord[]>([]);
  const [report, setReport] = useState<ProjectReport | null>(null);
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [recs, chgs] = await Promise.all([
      api.listRecommendations(summary.project_id),
      api.listChanges(summary.project_id),
    ]);
    setRecommendations(recs);
    setChanges(chgs);
    setReport(await api.getReport(summary.project_id));
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary.project_id]);

  async function runAction(name: string, action: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <h1>{summary.project_id}</h1>
          <p className="muted">
            {summary.languages.join(", ")} · {summary.frameworks.join(", ")} · {summary.component_count}{" "}
            components · {summary.test_count} tests ({summary.mapped_test_count} mapped)
          </p>
        </div>
        <div className="dashboard-actions">
          <button
            disabled={busy !== null}
            onClick={() => runAction("classify", () => api.classify(summary.project_id))}
          >
            {busy === "classify" ? "Classifying..." : "Classify"}
          </button>
          <button disabled={busy !== null} onClick={() => runAction("apply", () => api.apply(summary.project_id))}>
            {busy === "apply" ? "Applying..." : "Apply pending"}
          </button>
          <button
            disabled={busy !== null}
            onClick={() => runAction("detect", () => api.detectChanges(summary.project_id))}
          >
            {busy === "detect" ? "Checking..." : "Detect changes"}
          </button>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {report && (
        <div className="report-strip">
          <span>Retain: {report.retained}</span>
          <span>Modify: {report.modified}</span>
          <span>Remove: {report.removed}</span>
          <span>Generate: {report.generated}</span>
        </div>
      )}

      <div className="dashboard-columns">
        <section>
          <h2>Recommendations</h2>
          {recommendations.length === 0 && <p className="muted">No recommendations yet — run Classify.</p>}
          <div className="rec-list">
            {recommendations.map((rec) => (
              <RecommendationCard key={rec.id} recommendation={rec} onSelect={setSelected} />
            ))}
          </div>
        </section>

        <section>
          <h2>Recent changes</h2>
          <ChangeTimeline changes={changes} />
        </section>
      </div>

      {selected && <RecommendationDetailPage recommendation={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
