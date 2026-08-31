from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.analyzers.base import ImportEdge, LanguageAnalyzer, ParseResult
from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.repo_manager.workspace import Workspace

_BRIDGE_SCRIPT = Path(__file__).parent / "parser_bridge" / "parse.js"

EXCLUDED_DIRS = {".git", "node_modules", "dist", "build", "coverage", ".next", ".turbo", "out"}
SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
TEST_SUFFIXES = (
    ".test.js", ".test.jsx", ".test.ts", ".test.tsx",
    ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
)


class JSAnalyzer(LanguageAnalyzer):
    """Covers both JavaScript and TypeScript — component ids/language always
    use the "js:"/"javascript" prefix; pipeline._framework_map maps both the
    "javascript" and "typescript" stack-detector keys to the same test
    framework, so this simplification doesn't affect framework lookup."""

    language = "javascript"
    test_frameworks = ["jest", "mocha"]

    def detect(self, workspace: Workspace) -> bool:
        return (workspace.source_dir / "package.json").exists()

    def list_source_files(self, workspace: Workspace) -> list[Path]:
        root = workspace.source_dir
        return [
            p
            for p in root.rglob("*")
            if p.suffix in SOURCE_EXTENSIONS
            and not any(part in EXCLUDED_DIRS for part in p.relative_to(root).parts)
        ]

    def is_test_file(self, file_path: Path) -> bool:
        if file_path.name.endswith(TEST_SUFFIXES):
            return True
        return "__tests__" in file_path.parts

    def parse(self, file_path: Path, *, project_id: str, root: Path) -> ParseResult:
        rel_path = file_path.relative_to(root).as_posix()
        payload, error = _run_bridge(file_path)
        if error:
            return ParseResult(parse_errors=[f"{rel_path}: {error}"])
        if payload["parse_errors"]:
            return ParseResult(parse_errors=[f"{rel_path}: {e}" for e in payload["parse_errors"]])

        components: list[Component] = []
        for raw in payload["components"]:
            parent_id = None
            if raw["parent_qualified_name"] is not None:
                parent_id = f"js:{rel_path}:{raw['parent_qualified_name']}:{raw['parent_line']}"
            components.append(
                Component(
                    id=f"js:{rel_path}:{raw['qualified_name']}:{raw['line_start']}",
                    project_id=project_id,
                    language=self.language,
                    kind=raw["kind"],
                    name=raw["name"],
                    qualified_name=raw["qualified_name"],
                    file_path=rel_path,
                    line_start=raw["line_start"],
                    line_end=raw["line_end"],
                    signature=raw["signature"],
                    docstring=raw["docstring"],
                    parent_id=parent_id,
                    calls=raw["calls"],
                    metrics=ComponentMetrics(**raw["metrics"]),
                    content_hash=raw["content_hash"],
                )
            )
        imports = [ImportEdge(from_file=rel_path, to_module=i["to_module"]) for i in payload["imports"]]
        return ParseResult(components=components, imports=imports, parse_errors=[])

    def list_test_cases(
        self, file_path: Path, *, project_id: str, root: Path, framework: str
    ) -> list[TestCase]:
        rel_path = file_path.relative_to(root).as_posix()
        payload, error = _run_bridge(file_path)
        if error or payload["parse_errors"]:
            return []

        return [
            TestCase(
                id=f"js:{rel_path}:{raw['name']}:{raw['line_start']}",
                project_id=project_id,
                language=self.language,
                framework=framework,
                name=raw["name"],
                file_path=rel_path,
                line_start=raw["line_start"],
                line_end=raw["line_end"],
                content_hash=raw["content_hash"],
                origin="existing",
            )
            for raw in payload["test_cases"]
        ]


def _run_bridge(file_path: Path) -> tuple[dict | None, str | None]:
    if shutil.which("node") is None:
        return None, "Node.js is required to parse JS/TS files but was not found on PATH."
    try:
        proc = subprocess.run(
            ["node", str(_BRIDGE_SCRIPT), str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None, "parser bridge timed out"
    if proc.returncode != 0:
        return None, f"parser bridge failed: {proc.stderr.strip()[:500]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, f"parser bridge produced invalid JSON: {e}"
