import json
import re
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
        elif _has_unittest_testcase(root):
            frameworks.append("unittest")
        else:
            # Plain `def test_*():` functions with bare `assert` statements
            # — no explicit `import pytest` needed to run under pytest, and
            # no unittest.TestCase subclass either — are pytest's native
            # convention, not unittest's, so default here rather than to
            # unittest (which needs a TestCase to make sense of `self`).
            frameworks.append("pytest")

    if any((root / m).exists() for m in sig.JS_MARKERS):
        is_ts = any((root / m).exists() for m in sig.TS_MARKERS)
        languages.append("typescript" if is_ts else "javascript")
        if any((root / m).exists() for m in sig.JEST_CONFIG_MARKERS) or _package_json_has_dep(root, "jest"):
            frameworks.append("jest")
        elif _package_json_has_dep(root, "mocha"):
            frameworks.append("mocha")

    if any((root / m).exists() for m in sig.JAVA_MARKERS) or next(root.rglob("*.java"), None) is not None:
        languages.append("java")
        frameworks.append("junit")

    if any((root / m).exists() for m in sig.CPP_MARKERS) or next(root.rglob("*.cpp"), None) is not None:
        languages.append("cpp")
        if _cmake_references(root, "gtest") or _cmake_references(root, "GTest"):
            frameworks.append("gtest")
        elif _cmake_references(root, "Catch2") or _cmake_references(root, "catch2"):
            frameworks.append("catch2")
        else:
            frameworks.append("gtest")  # most common default; framework detection here is best-effort

    if (root / "go.mod").exists() or next(root.rglob("*.go"), None) is not None:
        languages.append("go")
        frameworks.append("testing")

    if next(root.rglob("*.csproj"), None) is not None or next(root.rglob("*.sln"), None) is not None:
        languages.append("csharp")
        if _csproj_references(root, "xunit"):
            frameworks.append("xunit")
        elif _csproj_references(root, "nunit"):
            frameworks.append("nunit")
        elif _csproj_references(root, "mstest"):
            frameworks.append("mstest")
        else:
            frameworks.append("xunit")  # most common default; framework detection here is best-effort

    return StackProfile(languages=languages, test_frameworks=frameworks)


def _cmake_references(root: Path, needle: str) -> bool:
    for f in list(root.rglob("CMakeLists.txt"))[:20]:
        try:
            if needle in f.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _csproj_references(root: Path, needle: str) -> bool:
    for f in list(root.rglob("*.csproj"))[:20]:
        try:
            if needle.lower() in f.read_text(encoding="utf-8", errors="ignore").lower():
                return True
        except OSError:
            continue
    return False


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


_UNITTEST_CLASS_PATTERN = re.compile(r"class\s+\w+\s*\(\s*(?:unittest\.)?TestCase\s*\)")


def _has_unittest_testcase(root: Path) -> bool:
    for f in list(root.rglob("*.py"))[:200]:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "import unittest" in text and _UNITTEST_CLASS_PATTERN.search(text):
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
