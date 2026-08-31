from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from app.analyzers.treesitter.base import TreeSitterAnalyzer
from app.knowledge_base.schema import Component, ComponentMetrics, TestCase
from app.repo_manager.workspace import Workspace


def _receiver_type_name(source: bytes, receiver: Node, text_fn) -> str | None:
    """Extract the type name a method's receiver is defined on, unwrapping
    a leading pointer_type if present (`func (c *Calculator) Foo()`)."""
    decl = receiver.named_children[0] if receiver.named_children else None
    if decl is None:
        return None
    type_node = decl.child_by_field_name("type")
    if type_node is None:
        return None
    if type_node.type == "pointer_type" and type_node.named_children:
        type_node = type_node.named_children[0]
    return text_fn(source, type_node)


class GoAnalyzer(TreeSitterAnalyzer):
    language = "go"
    test_frameworks = ["testing"]

    id_prefix = "go"
    ts_module_name = "tree_sitter_go"
    source_extensions = {".go"}

    decision_node_types = {"if_statement", "for_statement", "expression_switch_statement", "type_switch_statement", "select_statement"}
    nesting_node_types = {"if_statement", "for_statement", "expression_switch_statement", "type_switch_statement", "select_statement"}

    def detect(self, workspace: Workspace) -> bool:
        root = workspace.source_dir
        if (root / "go.mod").exists():
            return True
        return next(root.rglob("*.go"), None) is not None

    def is_test_file(self, file_path: Path) -> bool:
        return file_path.name.endswith("_test.go")

    def _extract_components(self, root: Node, source: bytes, rel_path: str, project_id: str) -> list[Component]:
        components: list[Component] = []
        struct_ids: dict[str, str] = {}  # struct type name -> component id, for method parent linkage

        for child in root.named_children:
            if child.type == "type_declaration":
                for spec in child.named_children:
                    if spec.type != "type_spec":
                        continue
                    type_node = spec.child_by_field_name("type")
                    if type_node is None or type_node.type != "struct_type":
                        continue
                    name_node = spec.child_by_field_name("name")
                    struct_name = self._text(source, name_node) if name_node else "anonymous"
                    struct_id = f"{self.id_prefix}:{rel_path}:{struct_name}:{self._line_start(child)}"
                    struct_ids[struct_name] = struct_id
                    components.append(
                        Component(
                            id=struct_id,
                            project_id=project_id,
                            language=self.language,
                            kind="class",
                            name=struct_name,
                            qualified_name=struct_name,
                            file_path=rel_path,
                            line_start=self._line_start(child),
                            line_end=self._line_end(child),
                            metrics=ComponentMetrics(loc=self._loc(child), cyclomatic_complexity=1, nesting_depth=0, num_params=0),
                            content_hash=self._segment_hash(source, child),
                        )
                    )

        for child in root.named_children:
            if child.type == "function_declaration":
                name_node = child.child_by_field_name("name")
                name = self._text(source, name_node) if name_node else "unknown"
                params_node = child.child_by_field_name("parameters")
                components.append(self._build_func_component(source, child, rel_path, project_id, name, name, None, params_node))
            elif child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                name = self._text(source, name_node) if name_node else "unknown"
                receiver = child.child_by_field_name("receiver")
                receiver_type = _receiver_type_name(source, receiver, self._text) if receiver else None
                qualname = f"{receiver_type}.{name}" if receiver_type else name
                parent_id = struct_ids.get(receiver_type) if receiver_type else None
                params_node = child.child_by_field_name("parameters")
                components.append(
                    self._build_func_component(source, child, rel_path, project_id, name, qualname, parent_id, params_node)
                )

        return components

    def _build_func_component(
        self, source: bytes, node: Node, rel_path: str, project_id: str, name: str,
        qualname: str, parent_id: str | None, params_node: Node | None,
    ) -> Component:
        return Component(
            id=f"{self.id_prefix}:{rel_path}:{qualname}:{self._line_start(node)}",
            project_id=project_id,
            language=self.language,
            kind="method" if parent_id else "function",
            name=name,
            qualified_name=qualname,
            file_path=rel_path,
            line_start=self._line_start(node),
            line_end=self._line_end(node),
            parent_id=parent_id,
            metrics=ComponentMetrics(
                loc=self._loc(node),
                cyclomatic_complexity=self._cyclomatic_complexity(node),
                nesting_depth=self._nesting_depth(node),
                num_params=self._num_params(params_node),
            ),
            content_hash=self._segment_hash(source, node),
        )

    def _extract_tests(
        self, root: Node, source: bytes, rel_path: str, project_id: str, framework: str
    ) -> list[TestCase]:
        tests: list[TestCase] = []
        for child in root.named_children:
            if child.type != "function_declaration":
                continue
            name_node = child.child_by_field_name("name")
            name = self._text(source, name_node) if name_node else ""
            if not name.startswith("Test"):
                continue
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
        return tests
