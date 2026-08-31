import json
from pathlib import Path

import pytest

from app.test_runner.pytest_runner import PytestRunner, _parse_coverage, _parse_json_report
from app.test_runner.sandbox_exec import DockerUnavailableError, docker_available, run_in_container
from app.repo_manager.workspace import Workspace


def test_docker_unavailable_raises_rather_than_falling_back_to_host_exec(tmp_path):
    if docker_available():
        pytest.skip("Docker is installed in this environment; unavailable-path not exercised")
    with pytest.raises(DockerUnavailableError):
        run_in_container(image="python:3.11-slim", workspace_dir=tmp_path, command=["true"])


def test_pytest_runner_reports_error_status_when_docker_missing(tmp_path):
    if docker_available():
        pytest.skip("Docker is installed in this environment; unavailable-path not exercised")
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()
    result = PytestRunner().run(ws)
    assert result.status == "error"
    assert "Docker" in result.stderr


def test_parse_json_report_counts_outcomes(tmp_path: Path):
    report = {
        "tests": [
            {"nodeid": "t.py::test_a", "outcome": "passed", "call": {"duration": 0.01}},
            {"nodeid": "t.py::test_b", "outcome": "failed", "call": {"duration": 0.02, "longrepr": "assert 1 == 2"}},
            {"nodeid": "t.py::test_c", "outcome": "skipped", "call": {}},
        ]
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    outcomes, totals = _parse_json_report(path)

    assert totals == {"total": 3, "passed": 1, "failed": 1, "errors": 0, "skipped": 1}
    assert len(outcomes) == 3
    assert outcomes[1].message == "assert 1 == 2"


def test_parse_coverage_reads_percent_covered(tmp_path: Path):
    path = tmp_path / "cov.json"
    path.write_text(json.dumps({"totals": {"percent_covered": 87.5}}), encoding="utf-8")
    assert _parse_coverage(path) == 87.5


def test_parse_coverage_missing_file_returns_none(tmp_path: Path):
    assert _parse_coverage(tmp_path / "missing.json") is None
