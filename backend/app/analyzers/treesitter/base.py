from __future__ import annotations

import hashlib
import importlib
from abc import abstractmethod
from pathlib import Path

from tree_sitter import Language, Node, Parser

from app.analyzers.base import LanguageAnalyzer, ParseResult
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

EXCLUDED_DIRS = {
    ".git", "node_modules", "dist", "build", "out", "bin", "obj", "target",
    ".gradle", ".idea", ".vs", "cmake-build-debug", "vendor",
}


class TreeSitterAnalyzer(LanguageAnalyzer):
    """Shared implementation for languages parsed via tree-sitter (Java,
    C/C++, Go, C#). Parsing setup, complexity/nesting/LOC metrics, file
    listing, and hashing are identical across these languages — only
    component/test extraction differs enough (different grammars, different
    test-framework conventions) to need a per-language override.
    """

    id_prefix: str
    ts_module_name: str
    source_extensions: set[str]
    decision_node_types: set[str] = set()
    nesting_node_types: set[str] = set()

    def __init__(self) -> None:
        self._parser: Parser | None = None

    def _get_parser(self) -> Parser:
        if self._parser is None:
            module = importlib.import_module(self.ts_module_name)
            self._parser = Parser(Language(module.language()))
        return self._parser

    def list_source_files(self, workspace: Workspace) -> list[Path]:
        root = workspace.source_dir
        return [
            p
            for p in root.rglob("*")
            if p.suffix in self.source_extensions
            and not any(part in EXCLUDED_DIRS for part in p.relative_to(root).parts)
        ]

    def _parse_tree(self, file_path: Path) -> tuple[Node, bytes] | None:
        try:
            source = file_path.read_bytes()
        except OSError:
            return None
        tree = self._get_parser().parse(source)
        return tree.root_node, source

    def _cyclomatic_complexity(self, node: Node) -> int:
        count = 1

        def walk(n: Node) -> None:
            nonlocal count
            if n.type in self.decision_node_types:
                count += 1
            for child in n.children:
                walk(child)

        walk(node)
        return count

    def _nesting_depth(self, node: Node) -> int:
        def walk(n: Node, depth: int) -> int:
            deepest = depth
            for child in n.children:
                next_depth = depth + 1 if child.type in self.nesting_node_types else depth
                deepest = max(deepest, walk(child, next_depth))
            return deepest

        return walk(node, 0)

    @staticmethod
    def _loc(node: Node) -> int:
        return node.end_point[0] - node.start_point[0] + 1

    @staticmethod
    def _num_params(params_node: Node | None) -> int:
        return len(params_node.named_children) if params_node is not None else 0

    @staticmethod
    def _text(source: bytes, node: Node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _segment_hash(source: bytes, node: Node) -> str:
        return "sha256:" + hashlib.sha256(source[node.start_byte : node.end_byte]).hexdigest()

    @staticmethod
    def _line_start(node: Node) -> int:
        return node.start_point[0] + 1

    @staticmethod
    def _line_end(node: Node) -> int:
        return node.end_point[0] + 1

    def parse(self, file_path: Path, *, project_id: str, root: Path) -> ParseResult:
        rel_path = file_path.relative_to(root).as_posix()
        parsed = self._parse_tree(file_path)
        if parsed is None:
            return ParseResult(parse_errors=[f"{rel_path}: could not read file"])
        tree_root, source = parsed
        if tree_root.has_error:
            # tree-sitter is error-tolerant and still returns a best-effort
            # tree, so we still try extraction rather than bailing out —
            # only genuinely unparseable content produces zero components.
            pass
        components = self._extract_components(tree_root, source, rel_path, project_id)
        return ParseResult(components=components, parse_errors=[])

    def list_test_cases(
        self, file_path: Path, *, project_id: str, root: Path, framework: str
    ) -> list[TestCase]:
        rel_path = file_path.relative_to(root).as_posix()
        parsed = self._parse_tree(file_path)
        if parsed is None:
            return []
        tree_root, source = parsed
        return self._extract_tests(tree_root, source, rel_path, project_id, framework)

    @abstractmethod
    def _extract_components(self, root: Node, source: bytes, rel_path: str, project_id: str) -> list[Component]: ...

    @abstractmethod
    def _extract_tests(
        self, root: Node, source: bytes, rel_path: str, project_id: str, framework: str
    ) -> list[TestCase]: ...
