from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.knowledge_base.schema import (
    ChangeRecord,
    DeploymentIssue,
    PerformanceRisk,
    PredictedRisk,
    Recommendation,
)
from app.knowledge_base.store import JSONFileStore
from app.reporting.audit_log import read_events
from app.repo_manager.workspace import Workspace
from app.tech_detector.detector import detect_stack
from app.test_runner.base import RunResult

DECISIONS = ("retain", "modify", "remove", "generate")


class FullReport(BaseModel):
    """Everything the framework knows about one project, in one document.

    Assembled from the knowledge base rather than recomputed, so the report
    reflects exactly what was decided and measured, and costs no model calls
    to produce.
    """

    project_id: str
    project_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    languages: list[str] = []
    frameworks: list[str] = []
    component_count: int = 0
    test_count: int = 0
    mapped_test_count: int = 0

    decision_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    recommendations: list[Recommendation] = []
    latest_run: RunResult | None = None
    run_history: list[RunResult] = []
    changes: list[ChangeRecord] = []
    deployment_issues: list[DeploymentIssue] = []
    performance_risks: list[PerformanceRisk] = []
    predicted_risks: list[PredictedRisk] = []
    audit_event_counts: dict[str, int] = {}
    audit_event_total: int = 0
    # A clean assessment and an assessment that never ran both produce
    # empty finding lists, so the audit trail is what distinguishes them.
    risk_assessment_run: bool = False


def collect(workspace: Workspace) -> FullReport:
    store = JSONFileStore()
    components = store.load_components(workspace)
    tests = store.load_tests(workspace)
    recommendations = store.load_recommendations(workspace)
    runs = store.load_runs(workspace)
    events = read_events(workspace)
    stack = detect_stack(workspace)

    return FullReport(
        project_id=workspace.project_id,
        project_name=workspace.display_name,
        languages=stack.languages,
        frameworks=stack.test_frameworks,
        component_count=len(components),
        test_count=len(tests),
        mapped_test_count=sum(1 for t in tests if t.target_component_ids),
        decision_counts={d: sum(1 for r in recommendations if r.decision == d) for d in DECISIONS},
        status_counts=dict(Counter(r.status for r in recommendations)),
        recommendations=recommendations,
        latest_run=runs[-1] if runs else None,
        run_history=runs,
        changes=store.load_changes(workspace),
        deployment_issues=store.load_deployment_issues(workspace),
        performance_risks=store.load_performance_risks(workspace),
        predicted_risks=store.load_predicted_risks(workspace),
        audit_event_counts=dict(Counter(e.get("event_type", "unknown") for e in events)),
        audit_event_total=len(events),
        risk_assessment_run=any(e.get("event_type") == "risk_assessment_completed" for e in events),
    )


def coverage_delta(report: FullReport) -> tuple[float, float] | None:
    """First and last measured coverage, when at least two runs recorded it.

    This is the headline figure: what coverage was before the AI pass and
    what it is now. Runs without coverage (a framework that does not report
    it, or a run that failed) are skipped rather than counted as zero.
    """
    measured = [r.coverage_percent for r in report.run_history if r.coverage_percent is not None]
    if len(measured) < 2:
        return None
    return measured[0], measured[-1]


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

def render_markdown(report: FullReport) -> str:
    out: list[str] = []
    w = out.append

    w(f"# Test Suite Report: {report.project_name}")
    w("")
    w(f"- **Project ID:** `{report.project_id}`")
    w(f"- **Generated:** {report.generated_at:%Y-%m-%d %H:%M} UTC")
    w(f"- **Stack:** {', '.join(report.languages) or 'not detected'}"
      f" / {', '.join(report.frameworks) or 'no test framework detected'}")
    w(f"- **Components analyzed:** {report.component_count}")
    w(f"- **Tests discovered:** {report.test_count} ({report.mapped_test_count} mapped to a component)")
    w("")

    w("## 1. Summary")
    w("")
    w("| Metric | Value |")
    w("| --- | --- |")
    for decision in DECISIONS:
        w(f"| {decision.capitalize()} | {report.decision_counts.get(decision, 0)} |")
    for status, count in sorted(report.status_counts.items()):
        w(f"| Recommendations {status.replace('_', ' ')} | {count} |")
    if report.latest_run:
        run = report.latest_run
        w(f"| Latest test run | {run.status} ({run.passed}/{run.total} passed) |")
        w(f"| Line coverage | {_fmt_cov(run.coverage_percent)} |")
    delta = coverage_delta(report)
    if delta:
        w(f"| Coverage change | {delta[0]:.1f}% to {delta[1]:.1f}% ({delta[1] - delta[0]:+.1f} pp) |")
    w("")

    w("## 2. Test Execution")
    w("")
    if not report.latest_run:
        w("No test run has been recorded for this project.")
    else:
        run = report.latest_run
        w(f"**Status:** {run.status} &nbsp;&nbsp; **Passed:** {run.passed}/{run.total} &nbsp;&nbsp; "
          f"**Failed:** {run.failed} &nbsp;&nbsp; **Errors:** {run.errors} &nbsp;&nbsp; "
          f"**Skipped:** {run.skipped} &nbsp;&nbsp; **Coverage:** {_fmt_cov(run.coverage_percent)} "
          f"&nbsp;&nbsp; **Duration:** {run.duration_ms / 1000:.1f}s")
        w("")
        failing = [o for o in run.outcomes if o.status not in ("passed", "skipped")]
        if failing:
            w(f"### Failing tests ({len(failing)})")
            w("")
            for outcome in failing:
                w(f"- **{outcome.name}** — {outcome.status}")
                if outcome.message:
                    w("")
                    w("  ```")
                    for line in outcome.message.strip().splitlines()[-20:]:
                        w(f"  {line}")
                    w("  ```")
            w("")
        elif run.total:
            w("All tests passed.")
            w("")
        if run.total == 0 and run.stderr:
            w("The run produced no results. Reported reason:")
            w("")
            w("```")
            w(run.stderr.strip()[-1500:])
            w("```")
            w("")

    w("## 3. AI Review Recommendations")
    w("")
    if not report.recommendations:
        w("No recommendations have been generated for this project.")
        w("")
    else:
        for decision in DECISIONS:
            group = [r for r in report.recommendations if r.decision == decision]
            if not group:
                continue
            w(f"### {decision.capitalize()} ({len(group)})")
            w("")
            w("| Component | Confidence | Status | Rationale |")
            w("| --- | --- | --- | --- |")
            for rec in group:
                reason = rec.failure_reason if rec.status == "failed" and rec.failure_reason else rec.rationale
                w(f"| `{rec.component_id}` | {rec.confidence:.0%} | {rec.status} | {_md_cell(reason)} |")
            w("")

    w("## 4. Detected Changes")
    w("")
    if not report.changes:
        w("No changes have been detected. Change detection requires the project to have been "
          "ingested from a repository and re-analyzed after a commit.")
    else:
        w("| Component | Change | Summary | Impacted |")
        w("| --- | --- | --- | --- |")
        for change in report.changes:
            w(f"| `{change.component_id}` | {change.change_type} | "
              f"{_md_cell(change.diff_summary or '')} | {len(change.impact_propagated_to)} |")
    w("")

    w("## 5. Risk Assessment")
    w("")
    groups = (
        ("Deployment readiness", report.deployment_issues),
        ("Performance risks", report.performance_risks),
        ("Predicted risks", report.predicted_risks),
    )
    if not any(items for _, items in groups):
        w("No findings. The assessment ran and reported nothing."
          if report.risk_assessment_run
          else "No risk assessment has been run for this project.")
        w("")
    else:
        for title, items in groups:
            if not items:
                continue
            w(f"### {title} ({len(items)})")
            w("")
            w("| Severity | Category | Finding |")
            w("| --- | --- | --- |")
            for item in items:
                w(f"| {item.severity} | {item.category} | {_md_cell(item.message)} |")
            w("")

    w("## 6. Audit Trail")
    w("")
    if not report.audit_event_total:
        w("No audit events recorded.")
    else:
        w(f"{report.audit_event_total} events recorded. Every AI recommendation and every test "
          "file write is logged, so the provenance of any generated test can be established.")
        w("")
        w("| Event | Count |")
        w("| --- | --- |")
        for event, count in sorted(report.audit_event_counts.items()):
            w(f"| {event} | {count} |")
    w("")

    return "\n".join(out) + "\n"


def _md_cell(text: str) -> str:
    """Flatten a value for a Markdown table cell: no newlines, no raw pipes."""
    return " ".join((text or "").split()).replace("|", "\\|")


def _fmt_cov(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.1f}%"


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

_HTML_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #1a1a1a;
       background: #fff; margin: 0; padding: 2.5rem 2rem; line-height: 1.55;
       max-width: 60rem; margin-inline: auto; }
h1 { font-size: 1.9rem; margin: 0 0 0.25rem; }
h2 { font-size: 1.25rem; margin: 2.2rem 0 0.75rem; padding-bottom: 0.3rem;
     border-bottom: 2px solid #e5e5e5; }
h3 { font-size: 1rem; margin: 1.4rem 0 0.5rem; color: #444; }
.meta { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
.meta div { margin: 0.1rem 0; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85em;
       background: #f4f4f5; padding: 0.1rem 0.3rem; border-radius: 3px; }
pre { background: #f7f7f8; border: 1px solid #e5e5e5; border-radius: 6px;
      padding: 0.75rem; overflow-x: auto; font-size: 0.8rem; white-space: pre-wrap;
      word-break: break-word; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; font-size: 0.88rem; }
th, td { border: 1px solid #e0e0e0; padding: 0.45rem 0.6rem; text-align: left;
         vertical-align: top; }
th { background: #f4f4f5; font-weight: 600; }
td.num, th.num { text-align: right; white-space: nowrap; }
.cards { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 1rem 0 0.5rem; }
.card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 0.7rem 1rem; min-width: 8rem; }
.card .label { font-size: 0.75rem; color: #666; text-transform: uppercase;
               letter-spacing: 0.03em; }
.card .value { font-size: 1.4rem; font-weight: 600; }
.pill { display: inline-block; font-size: 0.75rem; font-weight: 600; padding: 0.1rem 0.45rem;
        border-radius: 999px; border: 1px solid currentColor; white-space: nowrap; }
.ok { color: #1a7f37; } .bad { color: #c0392b; } .warn { color: #b35309; }
.muted { color: #666; }
.empty { color: #666; font-style: italic; }
@media print {
  body { padding: 0; max-width: none; }
  h2 { break-after: avoid; } table, pre { break-inside: avoid; }
}
"""


def render_html(report: FullReport) -> str:
    e = html.escape
    out: list[str] = []
    w = out.append

    w("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    w(f"<title>Test Suite Report - {e(report.project_name)}</title>")
    w(f"<style>{_HTML_CSS}</style></head><body>")

    w(f"<h1>Test Suite Report</h1>")
    w("<div class='meta'>")
    w(f"<div><strong>{e(report.project_name)}</strong></div>")
    w(f"<div>Project ID: <code>{e(report.project_id)}</code></div>")
    w(f"<div>Generated: {report.generated_at:%Y-%m-%d %H:%M} UTC</div>")
    w(f"<div>Stack: {e(', '.join(report.languages) or 'not detected')}"
      f" / {e(', '.join(report.frameworks) or 'no test framework detected')}</div>")
    w("</div>")

    # --- summary cards ---
    w("<h2>1. Summary</h2><div class='cards'>")
    w(_card("Components", report.component_count))
    w(_card("Tests", f"{report.test_count}", f"{report.mapped_test_count} mapped"))
    for decision in DECISIONS:
        w(_card(decision.capitalize(), report.decision_counts.get(decision, 0)))
    if report.latest_run:
        run = report.latest_run
        cls = "ok" if run.status == "passed" else "bad"
        w(_card("Test run", f"<span class='{cls}'>{e(run.status)}</span>", f"{run.passed}/{run.total} passed"))
        w(_card("Coverage", _fmt_cov(run.coverage_percent)))
    w("</div>")

    delta = coverage_delta(report)
    if delta:
        before, after = delta
        cls = "ok" if after >= before else "bad"
        w(f"<p>Coverage moved from <strong>{before:.1f}%</strong> to "
          f"<strong class='{cls}'>{after:.1f}%</strong> "
          f"(<span class='{cls}'>{after - before:+.1f} percentage points</span>) "
          f"across {len(report.run_history)} recorded runs.</p>")

    if report.status_counts:
        w("<table><tr><th>Recommendation status</th><th class='num'>Count</th></tr>")
        for status, count in sorted(report.status_counts.items()):
            w(f"<tr><td>{e(status.replace('_', ' '))}</td><td class='num'>{count}</td></tr>")
        w("</table>")

    # --- execution ---
    w("<h2>2. Test Execution</h2>")
    if not report.latest_run:
        w("<p class='empty'>No test run has been recorded for this project.</p>")
    else:
        run = report.latest_run
        w("<table><tr><th>Status</th><th class='num'>Passed</th><th class='num'>Failed</th>"
          "<th class='num'>Errors</th><th class='num'>Skipped</th><th class='num'>Coverage</th>"
          "<th class='num'>Duration</th></tr>")
        cls = "ok" if run.status == "passed" else "bad"
        w(f"<tr><td><span class='pill {cls}'>{e(run.status)}</span></td>"
          f"<td class='num'>{run.passed}</td><td class='num'>{run.failed}</td>"
          f"<td class='num'>{run.errors}</td><td class='num'>{run.skipped}</td>"
          f"<td class='num'>{_fmt_cov(run.coverage_percent)}</td>"
          f"<td class='num'>{run.duration_ms / 1000:.1f}s</td></tr></table>")

        failing = [o for o in run.outcomes if o.status not in ("passed", "skipped")]
        if failing:
            w(f"<h3>Failing tests ({len(failing)})</h3>")
            for outcome in failing:
                w(f"<p><span class='pill bad'>{e(outcome.status)}</span> <code>{e(outcome.name)}</code></p>")
                if outcome.message:
                    tail = "\n".join(outcome.message.strip().splitlines()[-25:])
                    w(f"<pre>{e(tail)}</pre>")
        elif run.total:
            w("<p class='ok'>All tests passed.</p>")
        if run.total == 0 and run.stderr:
            w("<h3>Why no results were produced</h3>")
            w(f"<pre>{e(run.stderr.strip()[-1500:])}</pre>")

    # --- recommendations ---
    w("<h2>3. AI Review Recommendations</h2>")
    if not report.recommendations:
        w("<p class='empty'>No recommendations have been generated for this project.</p>")
    else:
        for decision in DECISIONS:
            group = [r for r in report.recommendations if r.decision == decision]
            if not group:
                continue
            w(f"<h3>{decision.capitalize()} ({len(group)})</h3>")
            w("<table><tr><th>Component</th><th class='num'>Confidence</th><th>Status</th>"
              "<th>Rationale</th></tr>")
            for rec in group:
                reason = rec.failure_reason if rec.status == "failed" and rec.failure_reason else rec.rationale
                status_cls = {"applied": "ok", "failed": "bad"}.get(rec.status, "muted")
                w(f"<tr><td><code>{e(rec.component_id)}</code></td>"
                  f"<td class='num'>{rec.confidence:.0%}</td>"
                  f"<td><span class='{status_cls}'>{e(rec.status.replace('_', ' '))}</span></td>"
                  f"<td>{e(reason or '')}</td></tr>")
            w("</table>")

    # --- changes ---
    w("<h2>4. Detected Changes</h2>")
    if not report.changes:
        w("<p class='empty'>No changes have been detected. Change detection requires the project "
          "to have been ingested from a repository and re-analyzed after a commit.</p>")
    else:
        w("<table><tr><th>Component</th><th>Change</th><th>Summary</th>"
          "<th class='num'>Impacted</th></tr>")
        for change in report.changes:
            w(f"<tr><td><code>{e(change.component_id)}</code></td><td>{e(change.change_type)}</td>"
              f"<td>{e(change.diff_summary or '')}</td>"
              f"<td class='num'>{len(change.impact_propagated_to)}</td></tr>")
        w("</table>")

    # --- risks ---
    w("<h2>5. Risk Assessment</h2>")
    groups = (
        ("Deployment readiness", report.deployment_issues),
        ("Performance risks", report.performance_risks),
        ("Predicted risks", report.predicted_risks),
    )
    if not any(items for _, items in groups):
        w("<p class='empty'>No findings. The assessment ran and reported nothing.</p>"
          if report.risk_assessment_run
          else "<p class='empty'>No risk assessment has been run for this project.</p>")
    else:
        for title, items in groups:
            if not items:
                continue
            w(f"<h3>{title} ({len(items)})</h3>")
            w("<table><tr><th>Severity</th><th>Category</th><th>Finding</th></tr>")
            for item in items:
                cls = {"high": "bad", "medium": "warn"}.get(item.severity, "muted")
                w(f"<tr><td><span class='pill {cls}'>{e(item.severity)}</span></td>"
                  f"<td>{e(item.category)}</td><td>{e(item.message)}</td></tr>")
            w("</table>")

    # --- audit ---
    w("<h2>6. Audit Trail</h2>")
    if not report.audit_event_total:
        w("<p class='empty'>No audit events recorded.</p>")
    else:
        w(f"<p>{report.audit_event_total} events recorded. Every AI recommendation and every test "
          "file write is logged, so the provenance of any generated test can be established.</p>")
        w("<table><tr><th>Event</th><th class='num'>Count</th></tr>")
        for event, count in sorted(report.audit_event_counts.items()):
            w(f"<tr><td>{e(event)}</td><td class='num'>{count}</td></tr>")
        w("</table>")

    w("</body></html>")
    return "\n".join(out)


def _card(label: str, value, sub: str | None = None) -> str:
    sub_html = f"<div class='label'>{html.escape(sub)}</div>" if sub else ""
    return (f"<div class='card'><div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{value}</div>{sub_html}</div>")
