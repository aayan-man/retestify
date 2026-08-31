from .base import TestRunner
from .jest_runner import JestRunner
from .pytest_runner import PytestRunner

_RUNNERS: dict[str, TestRunner] = {
    "python": PytestRunner(),
    "javascript": JestRunner(),
    "typescript": JestRunner(),
}


def get_runner(language: str) -> TestRunner:
    if language not in _RUNNERS:
        raise ValueError(f"no test runner registered for language {language!r}")
    return _RUNNERS[language]


def register_runner(language: str, runner: TestRunner) -> None:
    _RUNNERS[language] = runner
