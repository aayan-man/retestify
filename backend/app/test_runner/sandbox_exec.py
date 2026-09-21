from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = "1"
DAEMON_PROBE_TIMEOUT_S = 15

# `docker run` uses 125 when the run itself failed (unreachable daemon, bad
# image), 126/127 when the container started but the command couldn't be
# invoked. All three mean the test suite never executed, as distinct from a
# suite that ran and reported failures.
DOCKER_RUN_FAILURE_EXIT_CODES = frozenset({125, 126, 127})


class DockerUnavailableError(Exception):
    pass


class ContainerExecutionError(Exception):
    """`docker run` failed before the test command could produce results."""


def docker_unavailable_reason() -> str | None:
    """None when Docker can actually run a container, otherwise a
    human-readable reason why it can't.

    Checking only that the `docker` binary is on PATH is not enough: an
    installed-but-not-started Docker Desktop leaves the CLI present while
    every `docker run` fails. That gap let a dead daemon be reported as a
    passing test run, so the daemon itself is probed here.
    """
    if shutil.which("docker") is None:
        return "Docker is required to execute target-repo tests but was not found on PATH."
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=DAEMON_PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"The Docker daemon did not respond within {DAEMON_PROBE_TIMEOUT_S}s."
    except OSError as e:
        return f"The Docker CLI could not be executed: {e}"

    if proc.returncode != 0:
        return (
            "The Docker CLI is installed but its daemon is not reachable "
            f"(docker info exited {proc.returncode}): {proc.stderr.strip()}"
        )
    return None


def docker_available() -> bool:
    return docker_unavailable_reason() is None


def run_in_container(
    *,
    image: str,
    workspace_dir: Path,
    command: list[str],
    timeout_s: int = 120,
    memory: str = DEFAULT_MEMORY,
    cpus: str = DEFAULT_CPUS,
    network: str = "none",
) -> subprocess.CompletedProcess:
    """Run `command` inside an ephemeral, network-isolated Docker container
    with the workspace bind-mounted read-write at /workspace (so a test run
    can write coverage/report files) and CPU/memory caps.

    Target-repo code and AI-generated code are both untrusted, so this is
    the only way test suites get executed — raises DockerUnavailableError
    rather than ever falling back to a bare host subprocess.

    Raises ContainerExecutionError if `docker run` itself fails, so that a
    container which never started can't be mistaken by the caller for a
    suite that ran and reported nothing.
    """
    reason = docker_unavailable_reason()
    if reason is not None:
        raise DockerUnavailableError(reason)

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        f"--network={network}",
        f"--memory={memory}",
        f"--cpus={cpus}",
        "-v",
        f"{workspace_dir.resolve()}:/workspace",
        "-w",
        "/workspace",
        image,
        *command,
    ]
    proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode in DOCKER_RUN_FAILURE_EXIT_CODES:
        raise ContainerExecutionError(
            f"docker run failed with exit code {proc.returncode} before the test "
            f"command could report results: {proc.stderr.strip()}"
        )
    return proc
