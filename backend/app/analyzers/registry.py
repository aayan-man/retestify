from app.repo_manager.workspace import Workspace

from .base import LanguageAnalyzer
from .cpp.analyzer import CppAnalyzer
from .csharp.analyzer import CSharpAnalyzer
from .go.analyzer import GoAnalyzer
from .java.analyzer import JavaAnalyzer
from .javascript.analyzer import JSAnalyzer
from .python.analyzer import PythonAnalyzer

_ANALYZERS: list[LanguageAnalyzer] = [
    PythonAnalyzer(),
    JSAnalyzer(),
    JavaAnalyzer(),
    CppAnalyzer(),
    GoAnalyzer(),
    CSharpAnalyzer(),
]


def all_analyzers() -> list[LanguageAnalyzer]:
    return list(_ANALYZERS)


def detect_all(workspace: Workspace) -> list[LanguageAnalyzer]:
    return [a for a in _ANALYZERS if a.detect(workspace)]


def get_analyzer(language: str) -> LanguageAnalyzer:
    for a in _ANALYZERS:
        if a.language == language:
            return a
    raise ValueError(f"no analyzer registered for language {language!r}")
