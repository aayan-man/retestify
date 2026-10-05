"""Which runner executes a given project's suite.

Runners are keyed by (language, framework) rather than language alone,
because one language commonly has several frameworks that need different
commands and produce different report formats -- a JS project may use jest
or vitest, a C# project xunit or nunit. Keying on language alone forced a
single choice per language and made "add vitest support" impossible
without replacing jest.

Adding a stack is one class implementing TestRunner plus one entry here
(or a register_runner call from outside this module, so a deployment can
add a runner without editing the framework).
"""

from __future__ import annotations

from .base import TestRunner
from .go_runner import GoRunner
from .jest_runner import JestRunner
from .maven_runner import MavenRunner
from .pytest_runner import PytestRunner

_RUNNERS: dict[tuple[str, str], TestRunner] = {
    # pytest runs unittest-style suites too, so both map to it.
    ("python", "pytest"): PytestRunner(),
    ("python", "unittest"): PytestRunner(),
    ("javascript", "jest"): JestRunner(),
    ("typescript", "jest"): JestRunner(),
    ("go", "testing"): GoRunner(),
    ("java", "junit"): MavenRunner(),
}

# Used when a caller names a language but no framework.
_LANGUAGE_DEFAULTS: dict[str, str] = {
    "python": "pytest",
    "javascript": "jest",
    "typescript": "jest",
    "go": "testing",
    "java": "junit",
}

# Languages the analyzers understand but that have no runner yet. Named
# explicitly so the error can say "not built yet" rather than the much more
# confusing "unknown language".
_ANALYZED_BUT_NOT_RUNNABLE = {
    "cpp": "GoogleTest or Catch2 via CTest",
    "csharp": "xUnit/NUnit/MSTest via `dotnet test`",
}


def supported_stacks() -> list[tuple[str, str]]:
    """Every (language, framework) pair that can actually be executed."""
    return sorted(_RUNNERS)


def get_runner(language: str, framework: str | None = None) -> TestRunner:
    """Resolve a runner for a language, optionally narrowed by framework.

    Falls back to the language's default framework when none is given, so
    callers that only know the language still work.
    """
    resolved = framework or _LANGUAGE_DEFAULTS.get(language)
    if resolved is not None and (language, resolved) in _RUNNERS:
        return _RUNNERS[(language, resolved)]

    if language in _ANALYZED_BUT_NOT_RUNNABLE:
        raise ValueError(
            f"{language!r} is analyzed and classified, but no test runner is built for it yet "
            f"(it would need {_ANALYZED_BUT_NOT_RUNNABLE[language]}). "
            f"Runnable today: {_describe_supported()}."
        )
    if framework is not None and language in _LANGUAGE_DEFAULTS:
        raise ValueError(
            f"no runner for framework {framework!r} in {language!r}. "
            f"Runnable today: {_describe_supported()}."
        )
    raise ValueError(f"no test runner registered for language {language!r}. Runnable today: {_describe_supported()}.")


def register_runner(language: str, runner: TestRunner, framework: str | None = None) -> None:
    """Add or replace a runner. `framework` defaults to the language's
    default so existing single-framework callers keep working."""
    resolved = framework or _LANGUAGE_DEFAULTS.get(language) or language
    _RUNNERS[(language, resolved)] = runner
    _LANGUAGE_DEFAULTS.setdefault(language, resolved)


def _describe_supported() -> str:
    return ", ".join(f"{lang}/{fw}" for lang, fw in supported_stacks())
