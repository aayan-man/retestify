from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Node

from app.analyzers.treesitter.base import TreeSitterAnalyzer
from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.repo_manager.workspace import Workspace

_MARKERS = ["CMakeLists.txt", "Makefile", "conanfile.txt", "meson.build"]
_TEST_MACROS = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P", "TEST_CASE", "SCENARIO"}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_") or "anonymous"


def _unwrap_declarator(node: Node) -> Node:
    """Pointer/reference return types wrap the function_declarator one level
    deeper (e.g. `int* foo()` -> pointer_declarator -> function_declarator)."""
    current = node
    while current.type in ("pointer_declarator", "reference_declarator") and current.child_by_field_name("declarator"):
        current = current.child_by_field_name("declarator")
    return current


class CppAnalyzer(TreeSitterAnalyzer):
    language = "cpp"
    test_frameworks = ["gtest", "catch2"]

    id_prefix = "cpp"
    ts_module_name = "tree_sitter_cpp"
    source_extensions = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h"}

    decision_node_types = {"if_statement", "for_statement", "while_statement", "do_statement", "catch_clause", "case_statement"}
    nesting_node_types = {"if_statement", "for_statement", "while_statement", "do_statement", "try_statement"}

    def detect(self, workspace: Workspace) -> bool:
        root = workspace.source_dir
        if any((root / m).exists() for m in _MARKERS):
            return True
        return next(root.rglob("*.cpp"), None) is not None or next(root.rglob("*.cc"), None) is not None

    def is_test_file(self, file_path: Path) -> bool:
        stem = file_path.stem.lower()
        return stem.endswith("test") or stem.endswith("tests") or stem.startswith("test_")

    def _function_name(self, source: bytes, func_def: Node) -> tuple[str, Node | None] | None:
        declarator = func_def.child_by_field_name("declarator")
        if declarator is None:
            return None
        declarator = _unwrap_declarator(declarator)
        if declarator.type != "function_declarator":
            return None
        name_node = declarator.child_by_field_name("declarator")
        if name_node is None or name_node.type not in ("identifier", "field_identifier"):
            return None
        return self._text(source, name_node), declarator.child_by_field_name("parameters")

    def _extract_components(self, root: Node, source: bytes, rel_path: str, project_id: str) -> list[Component]:
        components: list[Component] = []

        def walk(node: Node, parent_qualname: str | None, parent_id: str | None) -> None:
            for child in node.named_children:
                if child.type in ("class_specifier", "struct_specifier"):
                    name_node = child.child_by_field_name("name")
                    class_name = self._text(source, name_node) if name_node else "anonymous"
                    qualname = f"{parent_qualname}::{class_name}" if parent_qualname else class_name
                    class_id = f"{self.id_prefix}:{rel_path}:{qualname}:{self._line_start(child)}"
                    components.append(
                        Component(
                            id=class_id,
                            project_id=project_id,
                            language=self.language,
                            kind="class",
                            name=class_name,
                            qualified_name=qualname,
                            file_path=rel_path,
                            line_start=self._line_start(child),
                            line_end=self._line_end(child),
                            metrics=ComponentMetrics(loc=self._loc(child), cyclomatic_complexity=1, nesting_depth=0, num_params=0),
                            content_hash=self._segment_hash(source, child),
                        )
                    )
                    body = child.child_by_field_name("body")
                    if body is not None:
                        walk(body, qualname, class_id)
                elif child.type == "function_definition":
                    result = self._function_name(source, child)
                    if result is None:
                        continue
                    name, params_node = result
                    if name in _TEST_MACROS:
                        continue  # handled as a test case, not a component
                    qualname = f"{parent_qualname}::{name}" if parent_qualname else name
                    components.append(
                        Component(
                            id=f"{self.id_prefix}:{rel_path}:{qualname}:{self._line_start(child)}",
                            project_id=project_id,
                            language=self.language,
                            kind="method" if parent_id else "function",
                            name=name,
                            qualified_name=qualname,
                            file_path=rel_path,
                            line_start=self._line_start(child),
                            line_end=self._line_end(child),
                            parent_id=parent_id,
                            metrics=ComponentMetrics(
                                loc=self._loc(child),
                                cyclomatic_complexity=self._cyclomatic_complexity(child),
                                nesting_depth=self._nesting_depth(child),
                                num_params=self._num_params(params_node),
                            ),
                            content_hash=self._segment_hash(source, child),
                        )
                    )
                else:
                    walk(child, parent_qualname, parent_id)

        walk(root, None, None)
        return components

    def _extract_tests(
        self, root: Node, source: bytes, rel_path: str, project_id: str, framework: str
    ) -> list[TestCase]:
        tests: list[TestCase] = []

        def walk(node: Node) -> None:
            for child in node.named_children:
                if child.type == "function_definition":
                    result = self._function_name(source, child)
                    if result is not None:
                        name, params_node = result
                        if name in _TEST_MACROS:
                            args_text = self._text(source, params_node).strip("()") if params_node else name
                            test_name = f"test_{_slugify(args_text)}"
                            tests.append(
                                TestCase(
                                    id=f"{self.id_prefix}:{rel_path}:{test_name}:{self._line_start(child)}",
                                    project_id=project_id,
                                    language=self.language,
                                    framework=framework,
                                    name=test_name,
                                    file_path=rel_path,
                                    line_start=self._line_start(child),
                                    line_end=self._line_end(child),
                                    content_hash=self._segment_hash(source, child),
                                    origin="existing",
                                )
                            )
                walk(child)

        walk(root)
        return tests
