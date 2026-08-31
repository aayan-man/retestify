import json
from dataclasses import dataclass, field
from pathlib import Path

from app.repo_manager.workspace import Workspace

from . import signatures as sig


@dataclass
class StackProfile:
    languages: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)


def detect_stack(workspace: Workspace) -> StackProfile:
    root = workspace.source_dir
    languages: list[str] = []
    frameworks: list[str] = []

    if any((root / m).exists() for m in sig.PYTHON_MARKERS) or _has_py_files(root):
        languages.append("python")
        if any((root / m).exists() for m in sig.PYTEST_MARKERS) or _has_pytest_import(root):
            frameworks.append("pytest")
        else:
            frameworks.append("unittest")

    if any((root / m).exists() for m in sig.JS_MARKERS):
        is_ts = any((root / m).exists() for m in sig.TS_MARKERS)
        languages.append("typescript" if is_ts else "javascript")
        if any((root / m).exists() for m in sig.JEST_CONFIG_MARKERS) or _package_json_has_dep(root, "jest"):
            frameworks.append("jest")
        elif _package_json_has_dep(root, "mocha"):
            frameworks.append("mocha")

    return StackProfile(languages=languages, test_frameworks=frameworks)


def _has_py_files(root: Path) -> bool:
    return next(root.rglob("*.py"), None) is not None


def _has_pytest_import(root: Path) -> bool:
    for f in list(root.rglob("*.py"))[:200]:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "import pytest" in text or "from pytest" in text:
            return True
    return False


def _package_json_has_dep(root: Path, name: str) -> bool:
    pkg = root / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    return name in deps
