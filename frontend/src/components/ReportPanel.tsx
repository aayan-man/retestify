import { api } from "../api/client";
import type { ProjectReport, ProjectSummary } from "../types/kb";

interface Props {
  summary: ProjectSummary;
  report: ProjectReport | null;
  appliedCount: number;
  failedCount: number;
}

const FORMATS = [
  {
    format: "html" as const,
    label: "HTML",
    hint: "Self-contained; opens in any browser and prints to PDF",
  },
  { format: "md" as const, label: "Markdown", hint: "For pasting into a document or a pull request" },
  { format: "json" as const, label: "JSON", hint: "Structured data, for further processing" },
];

/** Download links for the full project report, with a short preview of what
 *  it will contain so the user knows whether it is worth downloading yet. */
export function ReportPanel({ summary, report, appliedCount, failedCount }: Props) {
  const run = report?.run_result ?? null;
  const decisions = report
    ? report.retained + report.modified + report.removed + report.generated
    : 0;

  return (
    <section className="report-section">
      <h2>Report</h2>
      <p className="muted">
        A full report of everything recorded for this project: the AI review decisions and their
        rationale, the latest test run with per-test outcomes and coverage, detected changes, risk
        findings, and the audit trail.
      </p>

      <ul className="report-contents">
        <li>
          {decisions > 0 ? `${decisions} recommendations` : "No recommendations yet"}
          {appliedCount > 0 && ` (${appliedCount} applied`}
          {appliedCount > 0 && failedCount > 0 && `, ${failedCount} failed`}
          {appliedCount > 0 && ")"}
        </li>
        <li>
          {run
            ? `Test run: ${run.status}, ${run.passed}/${run.total} passed, coverage ${
                run.coverage_percent === null ? "not measured" : `${run.coverage_percent.toFixed(1)}%`
              }`
            : "No test run recorded yet — run Run tests to include one"}
        </li>
        <li>
          {summary.component_count} components, {summary.test_count} tests analyzed
        </li>
      </ul>

      <div className="report-downloads">
        {FORMATS.map(({ format, label, hint }) => (
          <a
            key={format}
            className="download-link"
            href={api.reportUrl(summary.project_id, format)}
            download={`${summary.name}-test-report.${format}`}
            title={hint}
          >
            Download {label}
          </a>
        ))}
      </div>
      <p className="muted report-note">
        The report is built from stored results, so downloading it costs nothing and makes no AI
        calls. Run the steps above first to include their output.
      </p>
    </section>
  );
}
