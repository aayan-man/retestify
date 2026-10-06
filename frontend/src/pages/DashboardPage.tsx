import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ChangeTimeline } from "../components/ChangeTimeline";
import { RecommendationCard } from "../components/RecommendationCard";
import { ReportPanel } from "../components/ReportPanel";
import { RiskPanel } from "../components/RiskPanel";
import { TestResultsPanel } from "../components/TestResultsPanel";
import { RecommendationDetailPage } from "./RecommendationDetailPage";
import type { ChangeRecord, Job, ProjectReport, ProjectSummary, Recommendation, RiskAssessment } from "../types/kb";

const JOB_POLL_MS = 1000;

interface Props {
  summary: ProjectSummary;
  /** Return to the upload page to analyze a different project. */
  onBack: () => void;
}

export function DashboardPage({ summary, onBack }: Props) {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [changes, setChanges] = useState<ChangeRecord[]>([]);
  const [report, setReport] = useState<ProjectReport | null>(null);
  const [risks, setRisks] = useState<RiskAssessment | null>(null);
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ processed: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [recs, chgs, deploymentIssues, performanceRisks, predictedRisks] = await Promise.all([
      api.listRecommendations(summary.project_id),
      api.listChanges(summary.project_id),
      api.listDeploymentIssues(summary.project_id),
      api.listPerformanceRisks(summary.project_id),
      api.listPredictedRisks(summary.project_id),
    ]);
    setRecommendations(recs);
    setChanges(chgs);
    setReport(await api.getReport(summary.project_id));
    if (deploymentIssues.length || performanceRisks.length || predictedRisks.length) {
      setRisks({
        deployment_issues: deploymentIssues,
        performance_risks: performanceRisks,
        predicted_risks: predictedRisks,
      });
    }
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

  /** Start a background job and poll it to completion, surfacing progress. */
  async function runJob(name: string, start: () => Promise<Job>) {
    setBusy(name);
    setError(null);
    setProgress(null);
    try {
      let job = await start();
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
        job = await api.getJob(job.id);
        setProgress(job.total ? { processed: job.processed, total: job.total } : null);
      }
      if (job.status === "failed") {
        throw new Error(job.error ?? "the job failed without reporting a reason");
      }
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
      setProgress(null);
    }
  }

  function label(name: string, idle: string, active: string) {
    if (busy !== name) return idle;
    return progress ? `${active} ${progress.processed}/${progress.total}` : active;
  }

  const appliedCount = recommendations.filter((rec) => rec.status === "applied").length;
  const failedCount = recommendations.filter((rec) => rec.status === "failed").length;

  return (
    <div className="dashboard-page">
      {/* On its own row above the header, so the header keeps its original
          title-left / actions-right alignment. */}
      <button className="back-button" onClick={onBack} disabled={busy !== null}>
        &#8592; Analyze another project
      </button>

      <header className="dashboard-header">
        <div className="dashboard-identity">
          <h1>{summary.name}</h1>
          <p className="muted">
            {summary.languages.join(", ")} &middot; {summary.frameworks.join(", ")} &middot;{" "}
            {summary.component_count} components &middot; {summary.test_count} tests (
            {summary.mapped_test_count} mapped)
          </p>
          {/* Still shown: the id is what the CLI and the workspace folder
              use, so it has to stay findable. */}
          <p className="muted project-id">{summary.project_id}</p>
        </div>
        {/* Ordered to follow the workflow: inspect risks, decide, detect
            what changed, apply the decisions, verify by running, export. */}
        <div className="dashboard-actions">
          <button
            disabled={busy !== null}
            onClick={() =>
              runAction("assess", async () => setRisks(await api.assessRisks(summary.project_id)))
            }
          >
            {busy === "assess" ? "Assessing..." : "Assess Risks"}
          </button>
          <button
            disabled={busy !== null}
            onClick={() => runJob("classify", () => api.classify(summary.project_id))}
          >
            {label("classify", "Classify", "Classifying...")}
          </button>
          <button
            disabled={busy !== null}
            onClick={() => runAction("detect", () => api.detectChanges(summary.project_id))}
          >
            {busy === "detect" ? "Checking..." : "Detect changes"}
          </button>
          <button disabled={busy !== null} onClick={() => runJob("apply", () => api.apply(summary.project_id))}>
            {label("apply", "Modify", "Modifying...")}
          </button>
          <button
            disabled={busy !== null}
            onClick={() => runAction("tests", () => api.runTests(summary.project_id))}
          >
            {busy === "tests" ? "Running tests..." : "Run tests"}
          </button>
          <a
            className="download-link"
            href={api.downloadUrl(summary.project_id)}
            download={`${summary.name}.zip`}
          >
            Download .zip
          </a>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {report && (
        <div className="report-strip">
          <span>Retain: {report.retained}</span>
          <span>Modify: {report.modified}</span>
          <span>Remove: {report.removed}</span>
          <span>Generate: {report.generated}</span>
          {/* Applying is slow and otherwise leaves the view looking
              unchanged, so show what it actually did. */}
          {appliedCount > 0 && <span>Applied: {appliedCount}</span>}
          {failedCount > 0 && <span className="report-strip-failed">Failed: {failedCount}</span>}
        </div>
      )}

      {report?.run_result && <TestResultsPanel run={report.run_result} />}

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

      <section className="risk-section">
        <h2>Risk assessment</h2>
        <RiskPanel assessment={risks} />
      </section>

      <ReportPanel
        summary={summary}
        report={report}
        appliedCount={appliedCount}
        failedCount={failedCount}
      />

      {selected && <RecommendationDetailPage recommendation={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
