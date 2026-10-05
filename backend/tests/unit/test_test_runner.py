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


def test_requirements_file_is_installed_into_the_image(tmp_path):
    """A repo that declares dependencies gets them baked in, or its suite
    fails on ModuleNotFoundError before a single test runs."""
    from app.test_runner.pytest_runner import _dependency_layer

    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

    layer, digest = _dependency_layer(tmp_path)

    assert "COPY requirements.txt" in layer
    assert "pip install --no-cache-dir -r /tmp/requirements.txt" in layer
    assert digest


def test_dependency_digest_changes_with_the_requirements(tmp_path):
    """The digest feeds the image tag, so editing requirements must rebuild
    rather than silently reuse an image built from the old list."""
    from app.test_runner.pytest_runner import _dependency_layer

    req = tmp_path / "requirements.txt"
    req.write_text("flask\n", encoding="utf-8")
    first = _dependency_layer(tmp_path)[1]
    req.write_text("flask\nrequests\n", encoding="utf-8")

    assert _dependency_layer(tmp_path)[1] != first


def test_packaging_metadata_is_installed_from_the_project(tmp_path):
    from app.test_runner.pytest_runner import _dependency_layer

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    layer, _ = _dependency_layer(tmp_path)

    assert "pip install --no-cache-dir /src" in layer


def test_repo_declaring_no_dependencies_has_no_layer(tmp_path):
    from app.test_runner.pytest_runner import _dependency_layer

    assert _dependency_layer(tmp_path) is None


def test_missing_manifest_is_explained_in_the_result(monkeypatch, tmp_path):
    """Without a manifest the suite fails on imports, and the result must say
    why rather than leaving a bare 'error' with 0 tests."""
    monkeypatch.setattr(sandbox_exec, "docker_unavailable_reason", lambda: None)
    monkeypatch.setattr(sandbox_exec, "_image_exists", lambda tag: True)
    monkeypatch.setattr(
        sandbox_exec.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    ws = Workspace(project_id="proj_test", root=tmp_path)
    ws.ensure_dirs()

    result = PytestRunner().run(ws)

    assert result.status == "error"
    assert "declares no Python dependencies" in result.stderr
    assert "requirements.txt" in result.stderr


# --- Java / Maven runner -------------------------------------------------

SUREFIRE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="CalculatorTest" tests="4" errors="1" skipped="1" failures="1" time="1,234.5">
  <testcase name="testAdd" classname="CalculatorTest" time="0.042"/>
  <testcase name="testDivideFails" classname="CalculatorTest" time="0.001">
    <failure message="expected:&lt;3&gt; but was:&lt;5&gt;" type="java.lang.AssertionError">stack</failure>
  </testcase>
  <testcase name="testThrows" classname="CalculatorTest" time="0.002">
    <error message="cannot divide by zero" type="java.lang.IllegalArgumentException">stack</error>
  </testcase>
  <testcase name="testIgnored" classname="CalculatorTest" time="0"><skipped/></testcase>
</testsuite>
"""

EMPTY_TOTALS = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def _maven_workspace(tmp_path: Path, pom: str = "<project/>") -> Workspace:
    ws = Workspace(project_id="proj_java", root=tmp_path)
    ws.ensure_dirs()
    (ws.source_dir / "pom.xml").write_text(pom, encoding="utf-8")
    return ws


def _ok_container(**kwargs):
    return subprocess.CompletedProcess(["mvn"], 0, "", "")


def test_parse_surefire_reports_maps_every_outcome_kind(tmp_path: Path):
    """Surefire's <failure> (assertion) and <error> (unexpected exception) are
    different signals and must not be collapsed into one bucket."""
    from app.test_runner.maven_runner import _parse_surefire_reports

    reports = tmp_path / "surefire-reports"
    reports.mkdir()
    (reports / "TEST-CalculatorTest.xml").write_text(SUREFIRE_XML, encoding="utf-8")

    outcomes, totals = _parse_surefire_reports(reports)

    assert totals == {"total": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1}
    assert [o.status for o in outcomes] == ["passed", "failed", "error", "skipped"]
    assert outcomes[0].name == "CalculatorTest#testAdd"
    assert outcomes[0].duration_ms == 42
    assert outcomes[1].message == "expected:<3> but was:<5>"
    assert outcomes[2].message == "cannot divide by zero"


def test_parse_surefire_reports_missing_directory_is_empty(tmp_path: Path):
    from app.test_runner.maven_runner import _parse_surefire_reports

    assert _parse_surefire_reports(tmp_path / "nope") == ([], EMPTY_TOTALS)


def test_surefire_duration_tolerates_grouped_and_bad_numbers():
    from app.test_runner.maven_runner import _duration_ms

    assert _duration_ms("1,234.5") == 1234500
    assert _duration_ms(None) == 0
    assert _duration_ms("") == 0
    assert _duration_ms("not-a-number") == 0


def test_maven_runner_errors_without_a_pom(tmp_path: Path):
    from app.test_runner.maven_runner import MavenRunner

    ws = Workspace(project_id="proj_java", root=tmp_path)
    ws.ensure_dirs()

    result = MavenRunner().run(ws)

    assert result.status == "error"
    assert result.total == 0
    assert "no pom.xml" in result.stderr


def test_maven_runner_reports_error_when_no_surefire_report_is_produced(monkeypatch, tmp_path: Path):
    """A test-compile failure writes no reports; that is an error, not a pass."""
    from app.test_runner import maven_runner
    from app.test_runner.maven_runner import MavenRunner

    monkeypatch.setattr(maven_runner, "ensure_runner_image", lambda *a, **k: "img")
    monkeypatch.setattr(
        maven_runner,
        "run_in_container",
        lambda **k: subprocess.CompletedProcess(["mvn"], 1, "COMPILATION ERROR", ""),
    )

    result = MavenRunner().run(_maven_workspace(tmp_path))

    assert result.status == "error"
    assert result.total == 0
    assert "no surefire reports" in result.stderr


def test_maven_runner_clears_stale_reports_before_building(monkeypatch, tmp_path: Path):
    """Without this the previous run's passing XML would be parsed after a
    test-compile failure, reporting a false green."""
    from app.test_runner import maven_runner
    from app.test_runner.maven_runner import SUREFIRE_REPORT_DIR, MavenRunner

    ws = _maven_workspace(tmp_path)
    stale_dir = ws.source_dir / SUREFIRE_REPORT_DIR
    stale_dir.mkdir(parents=True)
    stale = stale_dir / "TEST-CalculatorTest.xml"
    stale.write_text(SUREFIRE_XML, encoding="utf-8")

    captured: dict = {}

    def fake_run_in_container(*, command, **kwargs):
        captured["command"] = command
        # Stands in for the container: the command's own `rm -rf` is what
        # removes the stale report before maven runs.
        stale.unlink()
        return subprocess.CompletedProcess(command, 1, "COMPILATION ERROR", "")

    monkeypatch.setattr(maven_runner, "ensure_runner_image", lambda *a, **k: "img")
    monkeypatch.setattr(maven_runner, "run_in_container", fake_run_in_container)

    result = MavenRunner().run(ws)

    assert f"rm -rf {SUREFIRE_REPORT_DIR}" in captured["command"][-1]
    assert result.status == "error" and result.total == 0


def test_maven_runner_runs_offline_and_never_resolves_at_run_time(monkeypatch, tmp_path: Path):
    """`--network=none` means run-time resolution can only fail, so the run
    must be offline (-o) and every fetch must happen at image build time."""
    from app.test_runner import maven_runner
    from app.test_runner.maven_runner import MavenRunner

    captured: dict = {}

    def fake_run_in_container(*, command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(maven_runner, "ensure_runner_image", lambda *a, **k: "img")
    monkeypatch.setattr(maven_runner, "run_in_container", fake_run_in_container)

    MavenRunner().run(_maven_workspace(tmp_path))

    script = captured["command"][-1]
    assert "mvn -o -B test" in script
    assert "go-offline" not in script, "dependency resolution belongs in the image build"
    assert "go-offline" in maven_runner.MAVEN_RUNNER_DOCKERFILE
    assert "COPY pom.xml" in maven_runner.MAVEN_RUNNER_DOCKERFILE


def test_maven_image_tag_tracks_the_pom(monkeypatch, tmp_path: Path):
    """The image's local repository is populated from the pom, so a changed
    pom must build a new image instead of reusing a stale one."""
    from app.test_runner import maven_runner
    from app.test_runner.maven_runner import MavenRunner

    tags: list[str] = []

    def fake_ensure(tag, dockerfile, context_dir=None):
        tags.append(tag)
        assert context_dir is not None, "the build needs a context to COPY pom.xml from"
        return tag

    monkeypatch.setattr(maven_runner, "ensure_runner_image", fake_ensure)
    monkeypatch.setattr(maven_runner, "run_in_container", _ok_container)

    runner = MavenRunner()
    runner.run(_maven_workspace(tmp_path, "<project><artifactId>a</artifactId></project>"))
    runner.run(_maven_workspace(tmp_path, "<project><artifactId>a</artifactId></project>"))
    runner.run(_maven_workspace(tmp_path, "<project><artifactId>b</artifactId></project>"))

    assert tags[0] == tags[1]
    assert tags[2] != tags[0]
    # Must be legal docker tags: one colon, no path separators.
    assert all(t.count(":") == 1 and "/" not in t for t in tags)


def test_maven_runner_targets_become_a_surefire_selector(monkeypatch, tmp_path: Path):
    from app.test_runner import maven_runner
    from app.test_runner.maven_runner import MavenRunner

    captured: dict = {}

    def fake_run_in_container(*, command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(maven_runner, "ensure_runner_image", lambda *a, **k: "img")
    monkeypatch.setattr(maven_runner, "run_in_container", fake_run_in_container)

    MavenRunner().run(_maven_workspace(tmp_path), targets=["CalculatorTest", "OtherTest"])

    assert "-Dtest=CalculatorTest,OtherTest" in captured["command"][-1]


def test_maven_runner_declares_its_language():
    from app.test_runner.maven_runner import MavenRunner

    assert MavenRunner.language == "java"


def test_maven_runner_does_not_fetch_dependencies_at_run_time():
    """Same regression guard as the pytest/jest runners: a network-isolated
    run cannot resolve anything from a remote repository."""
    from app.test_runner import maven_runner

    script = _code_without_comments(maven_runner.MavenRunner.run)
    assert "go-offline" not in script
    assert "dependency:get" not in script
