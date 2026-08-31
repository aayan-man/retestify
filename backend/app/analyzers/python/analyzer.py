from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from app.analyzers.base import ImportEdge, LanguageAnalyzer, ParseResult
from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.repo_manager.workspace import Workspace

from . import metrics as m

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".tox",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
}

PYTHON_MARKERS = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


class PythonAnalyzer(LanguageAnalyzer):
    language = "python"
    test_frameworks = ["pytest", "unittest"]

    def detect(self, workspace: Workspace) -> bool:
        root = workspace.source_dir
        if any((root / marker).exists() for marker in PYTHON_MARKERS):
            return True
        return next(root.rglob("*.py"), None) is not None

    def list_source_files(self, workspace: Workspace) -> list[Path]:
        root = workspace.source_dir
        return [
            p
            for p in root.rglob("*.py")
            if not any(part in EXCLUDED_DIRS for part in p.relative_to(root).parts)
        ]

    def is_test_file(self, file_path: Path) -> bool:
        name = file_path.name
        return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"

    def parse(self, file_path: Path, *, project_id: str, root: Path) -> ParseResult:
        rel_path = file_path.relative_to(root).as_posix()
        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return ParseResult(parse_errors=[f"{rel_path}: could not read file ({e})"])

        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError as e:
            return ParseResult(parse_errors=[f"{rel_path}: syntax error ({e})"])

        source_lines = source.splitlines()
        components: list[Component] = []
        imports: list[ImportEdge] = []
        module_qualname = rel_path[:-3].replace("/", ".") if rel_path.endswith(".py") else rel_path

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ImportEdge(from_file=rel_path, to_module=alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(ImportEdge(from_file=rel_path, to_module=node.module))

        def segment_hash(node: ast.AST) -> str:
            start = getattr(node, "lineno", 1) - 1
            end = getattr(node, "end_lineno", start + 1)
            segment = "\n".join(source_lines[start:end])
            return "sha256:" + hashlib.sha256(segment.encode("utf-8")).hexdigest()

        def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            try:
                return f"{prefix} {node.name}({ast.unparse(node.args)})"
            except Exception:
                return f"{prefix} {node.name}(...)"

        def called_names(node: ast.AST) -> list[str]:
            return sorted(
                {
                    n.func.id
                    for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                }
            )

        def visit_function(
            node: ast.FunctionDef | ast.AsyncFunctionDef,
            parent_qualname: str | None,
            parent_id: str | None,
            kind: str,
        ) -> None:
            qualname = f"{parent_qualname}.{node.name}" if parent_qualname else node.name
            comp_id = f"py:{rel_path}:{qualname}:{node.lineno}"
            components.append(
                Component(
                    id=comp_id,
                    project_id=project_id,
                    language="python",
                    kind=kind,
                    name=node.name,
                    qualified_name=f"{module_qualname}.{qualname}",
                    file_path=rel_path,
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    signature=signature(node),
                    docstring=ast.get_docstring(node),
                    parent_id=parent_id,
                    calls=called_names(node),
                    metrics=ComponentMetrics(
                        loc=m.loc(node),
                        cyclomatic_complexity=m.cyclomatic_complexity(node),
                        nesting_depth=m.nesting_depth(node),
                        num_params=m.num_params(node),
                    ),
                    content_hash=segment_hash(node),
                )
            )

        def visit_class(node: ast.ClassDef, parent_qualname: str | None) -> None:
            qualname = f"{parent_qualname}.{node.name}" if parent_qualname else node.name
            class_id = f"py:{rel_path}:{qualname}:{node.lineno}"
            components.append(
                Component(
                    id=class_id,
                    project_id=project_id,
                    language="python",
                    kind="class",
                    name=node.name,
                    qualified_name=f"{module_qualname}.{qualname}",
                    file_path=rel_path,
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    docstring=ast.get_docstring(node),
                    metrics=ComponentMetrics(
                        loc=m.loc(node), cyclomatic_complexity=1, nesting_depth=0, num_params=0
                    ),
                    content_hash=segment_hash(node),
                )
            )
            for child in node.body:
                if isinstance(child, _FUNCTION_NODES):
                    visit_function(child, qualname, class_id, "method")
                elif isinstance(child, ast.ClassDef):
                    visit_class(child, qualname)

        for node in tree.body:
            if isinstance(node, _FUNCTION_NODES):
                visit_function(node, None, None, "function")
            elif isinstance(node, ast.ClassDef):
                visit_class(node, None)

        return ParseResult(components=components, imports=imports, parse_errors=[])

    def list_test_cases(
        self, file_path: Path, *, project_id: str, root: Path, framework: str
    ) -> list[TestCase]:
        result = self.parse(file_path, project_id=project_id, root=root)
        return [
            TestCase(
                id=comp.id,
                project_id=project_id,
                language=self.language,
                framework=framework,
                name=comp.name,
                file_path=comp.file_path,
                line_start=comp.line_start,
                line_end=comp.line_end,
                content_hash=comp.content_hash,
                origin="existing",
            )
            for comp in result.components
            if comp.kind != "class" and comp.name.lower().startswith("test")
        ]
