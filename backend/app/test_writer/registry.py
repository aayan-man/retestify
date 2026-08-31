from typing import Callable

from app.ai_engine.schemas import GeneratedTest
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .cpp_writer import write_generated_test as _write_cpp
from .csharp_writer import write_generated_test as _write_csharp
from .go_writer import write_generated_test as _write_go
from .java_writer import write_generated_test as _write_java
from .js_writer import write_generated_test as _write_js
from .python_writer import write_generated_test as _write_python

TestWriterFn = Callable[[Workspace, Component, GeneratedTest, str], TestCase]

_WRITERS: dict[str, TestWriterFn] = {
    "python": _write_python,
    "javascript": _write_js,
    "typescript": _write_js,
    "java": _write_java,
    "cpp": _write_cpp,
    "go": _write_go,
    "csharp": _write_csharp,
}


def get_writer(language: str) -> TestWriterFn:
    if language not in _WRITERS:
        raise ValueError(f"no test writer registered for language {language!r}")
    return _WRITERS[language]


def register_writer(language: str, writer: TestWriterFn) -> None:
    _WRITERS[language] = writer
