from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace


class ImportEdge(BaseModel):
    from_file: str
    to_module: str


class ParseResult(BaseModel):
    components: list[Component] = []
    imports: list[ImportEdge] = []
    parse_errors: list[str] = []


class LanguageAnalyzer(ABC):
    """A pluggable per-language static analyzer.

    Every concrete analyzer (Python, JavaScript/TypeScript, ...) implements
    this interface so the rest of the pipeline never depends on a specific
    language's parser.
    """

    language: str
    test_frameworks: list[str] = []

    @abstractmethod
    def detect(self, workspace: Workspace) -> bool:
        """True if this analyzer applies to the workspace (marker files present)."""

    @abstractmethod
    def list_source_files(self, workspace: Workspace) -> list[Path]: ...

    @abstractmethod
    def parse(self, file_path: Path, *, project_id: str, root: Path) -> ParseResult:
        """Parse one file into Components. Must not raise on syntax errors —
        collect them into ParseResult.parse_errors instead."""

    @abstractmethod
    def is_test_file(self, file_path: Path) -> bool: ...

    @abstractmethod
    def list_test_cases(
        self, file_path: Path, *, project_id: str, root: Path, framework: str
    ) -> list[TestCase]:
        """Extract test cases from one test file. Kept separate from parse()
        because a "test case" isn't always a named function — Jest tests are
        `test(...)`/`it(...)` calls, not top-level declarations, so this
        needs its own per-language extraction logic rather than reusing the
        component-parsing convention that works for pytest/unittest."""
