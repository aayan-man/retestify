import json

from app.test_runner.jest_runner import _parse_jest_report


def _report(assertions: list[dict], key: str = "assertionResults") -> dict:
    return {"testResults": [{"name": "/workspace/calc.test.js", key: assertions}]}


def test_modern_jest_assertion_results_are_counted(tmp_path):
    """Jest nests per-test records under "assertionResults". Reading the
    suite's own "testResults" key instead reported every run as zero tests,
    so a passing suite came back as an error."""
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            _report(
                [
                    {"fullName": "add works", "status": "passed", "duration": 7},
                    {
                        "fullName": "divide throws",
                        "status": "failed",
                        "duration": 3,
                        "failureMessages": ["expected 1 to be 2"],
                    },
                    {"fullName": "skipped one", "status": "pending", "duration": 0},
                ]
            )
        ),
        encoding="utf-8",
    )

    outcomes, totals = _parse_jest_report(path)

    assert totals == {"total": 3, "passed": 1, "failed": 1, "errors": 0, "skipped": 1}
    failed = next(o for o in outcomes if o.status == "failed")
    assert "expected 1 to be 2" in (failed.message or "")


def test_older_jest_shape_still_parses(tmp_path):
    """The legacy "testResults" nesting is kept as a fallback so older jest
    and jest-compatible reporters keep working."""
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(_report([{"fullName": "legacy", "status": "passed", "duration": 1}], key="testResults")),
        encoding="utf-8",
    )

    _, totals = _parse_jest_report(path)

    assert totals["total"] == 1


def test_missing_or_unparseable_report_yields_nothing(tmp_path):
    assert _parse_jest_report(tmp_path / "missing.json")[1]["total"] == 0

    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert _parse_jest_report(bad)[1]["total"] == 0
