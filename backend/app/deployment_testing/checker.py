from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.knowledge_base.schema import DeploymentIssue
from app.repo_manager.workspace import Workspace

# Deliberately conservative patterns (real key/token shapes, not just the
# word "secret") to keep false positives low: CI/CD literature stresses
# that automated deployment gates need to trigger reliably, not constantly
# cry wolf and get ignored.
_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"sk-(ant|proj)?-[A-Za-z0-9_-]{20,}"), "API key (Anthropic/OpenAI-shaped)"),
    (re.compile(r"""(?i)(password|passwd|secret|api[_-]?key)\s*[:=]\s*["'][^"'\s]{8,}["']"""), "hardcoded credential-like literal"),
]

_ENV_VAR_PATTERNS = {
    "python": re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    "javascript": re.compile(r"""process\.env\.([A-Z_][A-Z0-9_]*)"""),
}

_ENV_DOC_FILES = [".env.example", ".env.sample", ".env.template", "README.md"]
_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def _iter_text_files(root: Path, extensions: set[str]) -> list[Path]:
    return [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in extensions
        and not any(part in _EXCLUDED_DIRS for part in p.relative_to(root).parts)
    ]


def _scan_for_secrets(workspace: Workspace, project_id: str) -> list[DeploymentIssue]:
    issues: list[DeploymentIssue] = []
    for path in _iter_text_files(workspace.source_dir, {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml"}):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        rel_path = path.relative_to(workspace.source_dir).as_posix()
        for lineno, line in enumerate(lines, start=1):
            for pattern, label in _SECRET_PATTERNS:
                if pattern.search(line):
                    issues.append(
                        DeploymentIssue(
                            id=f"depl_{uuid.uuid4().hex[:10]}",
                            project_id=project_id,
                            category="secret_exposure",
                            severity="high",
                            file_path=rel_path,
                            line=lineno,
                            message=f"Possible {label} committed to source — rotate it and move to an env var/secret store before deploying.",
                        )
                    )
                    break  # one finding per line is enough; avoid duplicate noise from overlapping patterns
    return issues


def _check_dependency_pinning(workspace: Workspace, project_id: str) -> list[DeploymentIssue]:
    issues: list[DeploymentIssue] = []
    root = workspace.source_dir

    requirements = root / "requirements.txt"
    if requirements.exists():
        unpinned = [
            line.strip()
            for line in requirements.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#") and "==" not in line and not line.strip().startswith("-")
        ]
        if unpinned:
            issues.append(
                DeploymentIssue(
                    id=f"depl_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    category="dependency_pinning",
                    severity="medium",
                    file_path="requirements.txt",
                    message=(
                        f"{len(unpinned)} dependenc{'y is' if len(unpinned) == 1 else 'ies are'} unpinned "
                        f"(no `==`) — reproducible deploys need exact versions, not floating ones."
                    ),
                )
            )

    package_json = root / "package.json"
    if package_json.exists() and not (root / "package-lock.json").exists() and not (root / "yarn.lock").exists() and not (root / "pnpm-lock.yaml").exists():
        issues.append(
            DeploymentIssue(
                id=f"depl_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                category="dependency_pinning",
                severity="medium",
                file_path="package.json",
                message="No lockfile (package-lock.json/yarn.lock/pnpm-lock.yaml) found — installs can drift between environments.",
            )
        )

    return issues


def _check_undocumented_env_vars(workspace: Workspace, project_id: str) -> list[DeploymentIssue]:
    root = workspace.source_dir
    documented: set[str] = set()
    for doc_name in _ENV_DOC_FILES:
        doc_path = root / doc_name
        if doc_path.exists():
            documented.update(re.findall(r"\b([A-Z_][A-Z0-9_]{2,})\b", doc_path.read_text(encoding="utf-8", errors="ignore")))

    referenced: dict[str, tuple[str, int]] = {}
    for language, pattern in _ENV_VAR_PATTERNS.items():
        extensions = {".py"} if language == "python" else {".js", ".jsx", ".ts", ".tsx"}
        for path in _iter_text_files(root, extensions):
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            rel_path = path.relative_to(root).as_posix()
            for lineno, line in enumerate(lines, start=1):
                for match in pattern.finditer(line):
                    referenced.setdefault(match.group(1), (rel_path, lineno))

    issues: list[DeploymentIssue] = []
    for var_name, (rel_path, lineno) in sorted(referenced.items()):
        if var_name in documented:
            continue
        issues.append(
            DeploymentIssue(
                id=f"depl_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                category="undocumented_env_var",
                severity="low",
                file_path=rel_path,
                line=lineno,
                message=f"`{var_name}` is read from the environment but isn't documented in .env.example/README — deploys will silently misconfigure it.",
            )
        )
    return issues


def _check_missing_ci_or_container(workspace: Workspace, project_id: str, component_count: int) -> list[DeploymentIssue]:
    root = workspace.source_dir
    has_ci = (root / ".github" / "workflows").exists() or (root / ".gitlab-ci.yml").exists()
    has_container = (root / "Dockerfile").exists()

    issues: list[DeploymentIssue] = []
    # Only worth flagging once a repo has enough surface area that manual
    # deploys become genuinely risky — matches the CI/CD literature's point
    # that IaC/repeatable environments matter most as systems grow.
    if component_count >= 10 and not has_ci:
        issues.append(
            DeploymentIssue(
                id=f"depl_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                category="missing_ci_or_container",
                severity="low",
                message="No CI workflow detected (.github/workflows or .gitlab-ci.yml) — deploys likely rely on manual steps, which the CI/CD literature flags as a common source of environment drift.",
            )
        )
    if component_count >= 10 and not has_container:
        issues.append(
            DeploymentIssue(
                id=f"depl_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                category="missing_ci_or_container",
                severity="low",
                message="No Dockerfile detected — without a pinned runtime image, 'works on my machine' environment differences are hard to rule out before deploying.",
            )
        )
    return issues


def check_deployment_readiness(workspace: Workspace, project_id: str, component_count: int) -> list[DeploymentIssue]:
    """Static, pre-deploy readiness checks over the target repo: hardcoded
    secrets, unpinned dependencies, undocumented required env vars, and
    (for larger repos) missing CI/container setup. All checks run against
    source on disk — no actual deployment happens."""
    return [
        *_scan_for_secrets(workspace, project_id),
        *_check_dependency_pinning(workspace, project_id),
        *_check_undocumented_env_vars(workspace, project_id),
        *_check_missing_ci_or_container(workspace, project_id, component_count),
    ]
