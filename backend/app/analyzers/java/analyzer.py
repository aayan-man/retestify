from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from app.analyzers.treesitter.base import TreeSitterAnalyzer
from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.repo_manager.workspace import Workspace

_MARKERS = ["pom.xml", "build.gradle", "build.gradle.kts"]
_TEST_ANNOTATIONS = {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory"}


class JavaAnalyzer(TreeSitterAnalyzer):
    language = "java"
    test_frameworks = ["junit"]

    id_prefix = "java"
    ts_module_name = "tree_sitter_java"
    source_extensions = {".java"}

    decision_node_types = {
        "if_statement", "for_statement", "enhanced_for_statement",
        "while_statement", "do_statement", "catch_clause", "switch_label",
    }
    nesting_node_types = {
        "if_statement", "for_statement", "enhanced_for_statement",
        "while_statement", "do_statement", "try_statement", "switch_expression",
    }

    def detect(self, workspace: Workspace) -> bool:
        root = workspace.source_dir
        if any((root / m).exists() for m in _MARKERS):
            return True
        return next(root.rglob("*.java"), None) is not None

    def is_test_file(self, file_path: Path) -> bool:
        name = file_path.name
        if name.endswith("Test.java") or name.endswith("Tests.java"):
            return True
        return "test" in {p.lower() for p in file_path.parts}

    def _extract_components(self, root: Node, source: bytes, rel_path: str, project_id: str) -> list[Component]:
        components: list[Component] = []

        def walk(node: Node, parent_qualname: str | None, parent_id: str | None) -> None:
            for child in node.named_children:
                if child.type == "class_declaration":
                    name_node = child.child_by_field_name("name")
                    class_name = self._text(source, name_node) if name_node else "Anonymous"
                    qualname = f"{parent_qualname}.{class_name}" if parent_qualname else class_name
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
                elif child.type in ("method_declaration", "constructor_declaration"):
                    name_node = child.child_by_field_name("name")
                    name = self._text(source, name_node) if name_node else "unknown"
                    qualname = f"{parent_qualname}.{name}" if parent_qualname else name
                    params_node = child.child_by_field_name("parameters")
                    signature = f"{name}{self._text(source, params_node) if params_node else '()'}"
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
                            signature=signature,
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

        def has_test_annotation(node: Node) -> bool:
            modifiers = next((c for c in node.children if c.type == "modifiers"), None)
            if modifiers is None:
                return False
            for ann in modifiers.named_children:
                if ann.type in ("marker_annotation", "annotation"):
                    name_node = ann.child_by_field_name("name")
                    if name_node and self._text(source, name_node) in _TEST_ANNOTATIONS:
                        return True
            return False

        def walk(node: Node) -> None:
            for child in node.named_children:
                if child.type == "method_declaration" and has_test_annotation(child):
                    name_node = child.child_by_field_name("name")
                    name = self._text(source, name_node) if name_node else "unknown"
                    tests.append(
                        TestCase(
                            id=f"{self.id_prefix}:{rel_path}:{name}:{self._line_start(child)}",
                            project_id=project_id,
                            language=self.language,
                            framework=framework,
                            name=name,
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
