import json

from app.knowledge_base.schema import Recommendation
from app.reporting.full_report import (
    FullReport,
    coverage_delta,
    render_html,
    render_markdown,
)
from app.test_runner.base import RunResult
from app.test_runner.base import TestOutcome as Outcome


def _rec(component_id, decision, status="pending_review", rationale="because", **kw):
    return Recommendation(
        id=f"rec_{component_id}",
        project_id="proj",
        component_id=component_id,
        decision=decision,
        rationale=rationale,
        confidence=0.9,
        status=status,
        **kw,
    )


def _run(**kw):
    defaults = dict(
        run_id="run_1",
        status="passed",
        total=3,
        passed=3,
        failed=0,
        errors=0,
        skipped=0,
        duration_ms=1200,
    )
    return RunResult(**{**defaults, **kw})


def _report(**kw) -> FullReport:
    defaults = dict(project_id="abc123", project_name="demo-project")
    return FullReport(**{**defaults, **kw})


def test_coverage_delta_needs_two_measured_runs():
    assert coverage_delta(_report(run_history=[_run(coverage_percent=80.0)])) is None

    delta = coverage_delta(
        _report(run_history=[_run(coverage_percent=80.0), _run(coverage_percent=95.5)])
    )
    assert delta == (80.0, 95.5)


def test_coverage_delta_skips_runs_without_coverage():
    """A framework that reports no coverage, or a run that failed, must not
    be counted as zero and drag the delta down."""
    history = [_run(coverage_percent=80.0), _run(coverage_percent=None), _run(coverage_percent=90.0)]

    assert coverage_delta(_report(run_history=history)) == (80.0, 90.0)


def test_markdown_contains_every_section():
    md = render_markdown(_report())

    for heading in (
        "## 1. Summary",
        "## 2. Test Execution",
        "## 3. AI Review Recommendations",
        "## 4. Detected Changes",
        "## 5. Risk Assessment",
        "## 6. Audit Trail",
    ):
        assert heading in md


def test_markdown_reports_decisions_and_failure_reasons():
    report = _report(
        recommendations=[
            _rec("py:a.py:f:1", "retain", rationale="covers both paths"),
            _rec("py:a.py:g:5", "generate", status="failed", failure_reason="rate limited"),
        ],
        decision_counts={"retain": 1, "modify": 0, "remove": 0, "generate": 1},
    )

    md = render_markdown(report)

    assert "covers both paths" in md
    # A failed recommendation shows why it failed, not its now-stale rationale.
    assert "rate limited" in md


def test_markdown_table_cells_survive_pipes_and_newlines():
    """A rationale containing a pipe or a newline would otherwise break the
    table it is rendered into."""
    report = _report(recommendations=[_rec("py:a.py:f:1", "retain", rationale="a | b\nsecond line")])

    md = render_markdown(report)
    row = next(line for line in md.splitlines() if "py:a.py:f:1" in line)

    assert "\\|" in row
    assert row.count("\n") == 0
    assert "second line" in row


def test_failing_tests_are_listed_with_their_message():
    run = _run(
        status="failed",
        total=2,
        passed=1,
        failed=1,
        outcomes=[
            Outcome(name="t.py::test_ok", status="passed", duration_ms=5),
            Outcome(name="t.py::test_bad", status="failed", duration_ms=7, message="assert 1 == 2"),
        ],
    )

    md = render_markdown(_report(latest_run=run, run_history=[run]))

    assert "t.py::test_bad" in md
    assert "assert 1 == 2" in md


def test_empty_run_explains_itself():
    run = _run(status="error", total=0, passed=0, stderr="Docker daemon is not reachable")

    md = render_markdown(_report(latest_run=run, run_history=[run]))

    assert "no results" in md
    assert "Docker daemon is not reachable" in md


def test_clean_risk_assessment_is_distinguished_from_one_never_run():
    not_run = render_markdown(_report(risk_assessment_run=False))
    clean = render_markdown(_report(risk_assessment_run=True))

    assert "No risk assessment has been run" in not_run
    assert "reported nothing" in clean


def test_html_escapes_content_rather_than_injecting_it():
    report = _report(
        project_name="<script>alert(1)</script>",
        recommendations=[_rec("py:a.py:f:1", "retain", rationale="5 < 6 & 7 > 2")],
    )

    out = render_html(report)

    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
    assert "5 &lt; 6 &amp; 7 &gt; 2" in out


def test_html_is_a_self_contained_document():
    """It has to open and print without fetching anything, so no external
    stylesheet or script references."""
    out = render_html(_report())

    assert out.startswith("<!doctype html>")
    assert "</html>" in out
    assert "<style>" in out
    assert "src=" not in out and "<link" not in out


def test_report_serialises_to_json():
    report = _report(
        recommendations=[_rec("py:a.py:f:1", "retain")],
        latest_run=_run(coverage_percent=85.7),
    )

    data = json.loads(report.model_dump_json())

    assert data["project_name"] == "demo-project"
    assert data["latest_run"]["coverage_percent"] == 85.7
    assert data["recommendations"][0]["component_id"] == "py:a.py:f:1"
