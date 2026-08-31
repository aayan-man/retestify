from typing import Callable

from app.ai_engine.schemas import GeneratedTest
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .js_writer import write_generated_test as _write_js
from .python_writer import write_generated_test as _write_python

TestWriterFn = Callable[[Workspace, Component, GeneratedTest, str], TestCase]

_WRITERS: dict[str, TestWriterFn] = {
    "python": _write_python,
    "javascript": _write_js,
    "typescript": _write_js,
}


def get_writer(language: str) -> TestWriterFn:
    if language not in _WRITERS:
        raise ValueError(f"no test writer registered for language {language!r}")
    return _WRITERS[language]


def register_writer(language: str, writer: TestWriterFn) -> None:
    _WRITERS[language] = writer
