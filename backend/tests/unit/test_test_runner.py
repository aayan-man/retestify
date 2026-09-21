import json
import subprocess
from pathlib import Path

import pytest

from app.test_runner import sandbox_exec
from app.test_runner.base import overall_status
from app.test_runner.pytest_runner import PytestRunner, _parse_coverage, _parse_json_report
from app.test_runner.sandbox_exec import (
    ContainerExecutionError,
    DockerUnavailableError,
    docker_available,
    run_in_container,
)
from app.repo_manager.workspace import Workspace


def test_zero_tests_is_an_error_not_a_pass():
    """A run that produced no results must never report "passed" — an empty
    report means the suite never ran, and a false green is the worst way
    for a test tool to be wrong."""
    assert overall_status({"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}) == "error"


def test_overall_status_passed_only_when_tests_ran_clean():
    assert overall_status({"total": 3, "passed": 3, "failed": 0, "errors": 0, "skipped": 0}) == "passed"
    assert overall_status({"total": 3, "passed": 2, "failed": 1, "errors": 0, "skipped": 0}) == "failed"
    assert overall_status({"total": 3, "passed": 2, "failed": 0, "errors": 1, "skipped": 0}) == "failed"


def test_docker_reported_unavailable_when_cli_exists_but_daemon_is_down(monkeypatch):
    """Docker Desktop installed but not started leaves the CLI on PATH while
    every `docker run` fails, which previously read as a passing run."""
    monkeypatch.setattr(sandbox_exec.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "Cannot connect to the Docker daemon"),
    )

    reason = sandbox_exec.docker_unavailable_reason()

    assert reason is not None and "daemon is not reachable" in reason
    assert docker_available() is False


def test_run_in_container_raises_when_docker_run_itself_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 125, "", "no such image"),
    )

    with pytest.raises(ContainerExecutionError, match="125"):
        run_in_container(image="python:3.11-slim", workspace_dir=tmp_path, command=["true"])


def test_run_in_container_returns_normally_when_the_suite_itself_fails(monkeypatch, tmp_path):
    """A non-zero exit from the test command is a real result, not a
    container failure, so it must still come back to the caller."""
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "2 failed", ""),
    )

    proc = run_in_container(image="python:3.11-slim", workspace_dir=tmp_path, command=["true"])

    assert proc.returncode == 1
    assert proc.stdout == "2 failed"


def test_pytest_runner_reports_error_when_no_report_is_produced(monkeypatch, tmp_path):
    """End-to-end guard on the original bug: the container 'runs' but writes
    no report, and the result must be an error mentioning why."""
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()

    result = PytestRunner().run(ws)

    assert result.status == "error"
    assert result.total == 0
    assert "no JSON report" in result.stderr


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
