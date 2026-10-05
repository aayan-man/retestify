import pytest

from app.test_runner.go_runner import GoRunner
from app.test_runner.pytest_runner import PytestRunner
from app.test_runner.registry import get_runner, register_runner, supported_stacks


def test_language_alone_still_resolves():
    """Callers that only know the language keep working."""
    assert isinstance(get_runner("python"), PytestRunner)
    assert isinstance(get_runner("go"), GoRunner)


def test_framework_selects_between_runners_for_one_language():
    """The point of keying on (language, framework): pytest also runs
    unittest suites, so both frameworks resolve, while an unknown one for a
    supported language is rejected rather than silently falling back."""
    assert isinstance(get_runner("python", "pytest"), PytestRunner)
    assert isinstance(get_runner("python", "unittest"), PytestRunner)

    with pytest.raises(ValueError, match="no runner for framework"):
        get_runner("python", "nose")


def test_java_is_runnable_via_maven():
    from app.test_runner.maven_runner import MavenRunner

    assert isinstance(get_runner("java"), MavenRunner)
    assert isinstance(get_runner("java", "junit"), MavenRunner)


def test_analyzed_languages_without_a_runner_say_so_specifically():
    """cpp/csharp are analyzed and classified; the error must not read as
    'unknown language' when the real state is 'runner not built yet'."""
    for language in ("cpp", "csharp"):
        with pytest.raises(ValueError) as exc:
            get_runner(language)
        assert "no test runner is built for it yet" in str(exc.value)
        assert "Runnable today" in str(exc.value)


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="no test runner registered"):
        get_runner("cobol")


def test_a_new_stack_can_be_registered_without_editing_the_registry():
    """The extensibility claim, exercised."""

    class DummyRunner(PytestRunner):
        language = "elixir"

    register_runner("elixir", DummyRunner(), framework="exunit")

    assert isinstance(get_runner("elixir", "exunit"), DummyRunner)
    assert ("elixir", "exunit") in supported_stacks()


def test_supported_stacks_lists_real_pairs():
    stacks = supported_stacks()
    assert ("python", "pytest") in stacks
    assert ("go", "testing") in stacks
    assert all(isinstance(lang, str) and isinstance(fw, str) for lang, fw in stacks)
