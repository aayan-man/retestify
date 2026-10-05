import json

from app.test_runner.go_runner import _parse_coverage_total, _parse_go_json


def test_go_json_stream_is_parsed_into_outcomes(tmp_path):
    """Events are built with json.dumps rather than hand-written strings, so
    the embedded newline in Output is escaped the way `go test -json` emits
    it."""
    events = [
        {"Action": "run", "Package": "sample", "Test": "TestAdd"},
        {"Action": "output", "Package": "sample", "Test": "TestAdd", "Output": "ok\n"},
        {"Action": "pass", "Package": "sample", "Test": "TestAdd", "Elapsed": 0.01},
        {"Action": "output", "Package": "sample", "Test": "TestSub", "Output": "boom\n"},
        {"Action": "fail", "Package": "sample", "Test": "TestSub", "Elapsed": 0.02},
        {"Action": "skip", "Package": "sample", "Test": "TestMul", "Elapsed": 0},
        # Package-level event: carries no Test key, so it must not be counted.
        {"Action": "pass", "Package": "sample", "Elapsed": 0.5},
    ]
    path = tmp_path / "report.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    outcomes, totals = _parse_go_json(path)

    assert totals == {"total": 3, "passed": 1, "failed": 1, "errors": 0, "skipped": 1}
    failed = next(o for o in outcomes if o.status == "failed")
    assert "boom" in (failed.message or "")
    assert next(o for o in outcomes if o.status == "passed").duration_ms == 10


def test_non_json_build_errors_do_not_break_parsing(tmp_path):
    """A compile failure prints bare text before any events; it must be
    skipped rather than aborting the parse."""
    path = tmp_path / "report.jsonl"
    path.write_text(
        "# command-line-arguments\n"
        "syntax error\n" + json.dumps({"Action": "pass", "Package": "p", "Test": "T", "Elapsed": 0}) + "\n",
        encoding="utf-8",
    )

    _, totals = _parse_go_json(path)

    assert totals["total"] == 1


def test_missing_report_yields_no_results(tmp_path):
    outcomes, totals = _parse_go_json(tmp_path / "missing.jsonl")
    assert outcomes == [] and totals["total"] == 0


def test_coverage_total_is_read_from_the_last_line():
    stdout = "sample/calc.go:3:\tAdd\t100.0%\ntotal:\t(statements)\t50.0%\n"
    assert _parse_coverage_total(stdout) == 50.0


def test_coverage_absent_returns_none():
    assert _parse_coverage_total("no coverage here\n") is None
