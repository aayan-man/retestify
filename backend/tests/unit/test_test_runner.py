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


def test_runner_image_tag_is_stable_and_differs_per_base_image():
    """A new base image must produce a new tag, or changing
    APP_TEST_RUNNER_DOCKER_IMAGE_PYTHON would silently reuse an image built
    from the old one."""
    tag = sandbox_exec.runner_image_tag("python:3.11-slim", "pytest")

    assert tag == sandbox_exec.runner_image_tag("python:3.11-slim", "pytest")
    assert tag != sandbox_exec.runner_image_tag("python:3.12-slim", "pytest")
    assert tag != sandbox_exec.runner_image_tag("python:3.11-slim", "jest")
    # Must be a legal docker tag: one colon, no path separators.
    assert tag.count(":") == 1 and "/" not in tag


def test_existing_runner_image_is_not_rebuilt(monkeypatch):
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(sandbox_exec, "_image_exists", lambda tag: True)
    monkeypatch.setattr(
        sandbox_exec.subprocess, "run", lambda *a, **k: pytest.fail("should not rebuild an existing image")
    )

    assert sandbox_exec.ensure_runner_image("tag:1", "FROM x") == "tag:1"


def test_missing_runner_image_is_built(monkeypatch):
    calls = []
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(sandbox_exec, "_image_exists", lambda tag: False)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("input")))
        return subprocess.CompletedProcess(cmd, 0, "sha256:abc", "")

    monkeypatch.setattr(sandbox_exec.subprocess, "run", fake_run)

    assert sandbox_exec.ensure_runner_image("tag:1", "FROM base") == "tag:1"
    cmd, dockerfile = calls[0]
    assert cmd[:3] == ["docker", "build", "-q"] and cmd[-1] == "-"
    assert dockerfile == "FROM base", "the Dockerfile must be piped in on stdin"


def test_failed_image_build_raises_rather_than_running_without_tooling(monkeypatch):
    """The whole point of the image is that the tooling cannot be installed
    during a network-isolated run, so a failed build must stop the run."""
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(sandbox_exec, "_image_exists", lambda tag: False)
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "no space left on device"),
    )

    with pytest.raises(ContainerExecutionError, match="network access"):
        sandbox_exec.ensure_runner_image("tag:1", "FROM base")


def test_image_build_refuses_when_docker_is_unusable(monkeypatch):
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: "daemon down")

    with pytest.raises(DockerUnavailableError, match="daemon down"):
        sandbox_exec.ensure_runner_image("tag:1", "FROM base")


def _code_without_comments(func) -> str:
    import inspect

    return chr(10).join(
        line for line in inspect.getsource(func).splitlines() if not line.lstrip().startswith("#")
    )


def test_runners_do_not_install_tooling_at_run_time():
    """Regression guard: an install inside the run can never succeed, because
    run_in_container disables networking. Comments are stripped first, since
    they legitimately mention the commands being avoided."""
    from app.test_runner import jest_runner, pytest_runner

    assert "pip install" not in _code_without_comments(pytest_runner.PytestRunner.run)
    assert "npm install" not in _code_without_comments(jest_runner.JestRunner.run)


def test_container_runs_stay_network_isolated_by_default():
    import inspect

    assert inspect.signature(sandbox_exec.run_in_container).parameters["network"].default == "none"
