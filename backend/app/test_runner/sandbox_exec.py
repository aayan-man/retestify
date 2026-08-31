from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = "1"


class DockerUnavailableError(Exception):
    pass


def docker_available() -> bool:
    return shutil.which("docker") is not None


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
    """
    if not docker_available():
        raise DockerUnavailableError(
            "Docker is required to execute target-repo tests but was not found on PATH."
        )

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
    return subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout_s)
