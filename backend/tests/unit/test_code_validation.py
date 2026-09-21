import pytest

from app.ai_engine.code_validation import (
    GeneratedCodeError,
    normalize_generated_code,
    unresolved_repo_import,
)


def test_valid_python_passes_through_unchanged():
    code = "def test_thing():\n    assert 1 == 1\n"
    assert normalize_generated_code(code, "python") == code.strip()


def test_escaped_newlines_are_repaired_when_that_fixes_the_parse():
    """The failure that broke a whole test file: the provider emitted "\\n"
    as two literal characters, collapsing the test onto one line."""
    broken = "import pytest\\ndef test_thing():\\n    assert True"

    result = normalize_generated_code(broken, "python")

    assert "\\n" not in result
    assert result.splitlines()[0] == "import pytest"


def test_genuinely_broken_python_is_rejected():
    with pytest.raises(GeneratedCodeError, match="not syntactically valid"):
        normalize_generated_code("def test_thing(:\n    assert True", "python")


def test_empty_code_is_rejected():
    with pytest.raises(GeneratedCodeError, match="empty"):
        normalize_generated_code("   \n  ", "python")


def test_escaped_newlines_inside_a_string_literal_are_left_alone():
    """Code that already parses is never touched, so a test asserting on
    newline characters keeps its escape sequences."""
    code = 'def test_thing():\n    assert "a\\nb".count("\\n") == 1\n'

    result = normalize_generated_code(code, "python")

    assert result == code.strip()
    assert '"a\\nb"' in result


def test_hallucinated_import_from_the_module_under_test_is_caught(tmp_path):
    """The real failure: the model invented a class and imported it from the
    module it was asked to test."""
    (tmp_path / "six.py").write_text("def ensure_str(s):\n    return s\n", encoding="utf-8")

    message = unresolved_repo_import("from six import MyClass\n", tmp_path)

    assert message is not None
    assert "MyClass" in message and "six" in message


def test_real_symbol_is_accepted(tmp_path):
    (tmp_path / "six.py").write_text("def ensure_str(s):\n    return s\n", encoding="utf-8")
    assert unresolved_repo_import("from six import ensure_str\n", tmp_path) is None


def test_names_defined_inside_conditionals_still_resolve(tmp_path):
    """six.py defines much of its API inside `if PY3:` blocks — treating only
    the outermost statements as definitions would reject valid imports."""
    (tmp_path / "six.py").write_text(
        "import sys\n"
        "if sys.version_info[0] == 3:\n"
        "    def ensure_text(s):\n"
        "        return s\n"
        "else:\n"
        "    def ensure_text(s):\n"
        "        return s\n"
        "try:\n"
        "    CONSTANT = 1\n"
        "except ImportError:\n"
        "    CONSTANT = 2\n",
        encoding="utf-8",
    )

    assert unresolved_repo_import("from six import ensure_text\n", tmp_path) is None
    assert unresolved_repo_import("from six import CONSTANT\n", tmp_path) is None


def test_modules_binding_names_dynamically_are_not_checked(tmp_path):
    """Names injected via globals() can't be seen statically, so such a
    module is skipped rather than risking a false rejection."""
    (tmp_path / "dyn.py").write_text("globals()['injected'] = 1\n", encoding="utf-8")
    assert unresolved_repo_import("from dyn import injected\n", tmp_path) is None


def test_third_party_and_stdlib_imports_are_left_alone(tmp_path):
    code = "import pytest\nfrom collections import OrderedDict\nfrom nowhere import Thing\n"
    assert unresolved_repo_import(code, tmp_path) is None


def test_package_init_and_star_imports_are_handled(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("class Widget:\n    pass\n", encoding="utf-8")

    assert unresolved_repo_import("from pkg import Widget\n", tmp_path) is None
    assert unresolved_repo_import("from pkg import *\n", tmp_path) is None
    assert unresolved_repo_import("from pkg import Missing\n", tmp_path) is not None


def test_submodule_of_a_single_file_module_is_not_checked(tmp_path):
    """`six.moves` is assembled at runtime and has no file of its own, so
    importing from it must not be judged against six.py's own names."""
    (tmp_path / "six.py").write_text("def ensure_str(s):\n    return s\n", encoding="utf-8")

    assert unresolved_repo_import("from six.moves import zip_longest\n", tmp_path) is None


def test_unparseable_generated_code_defers_to_the_syntax_check(tmp_path):
    assert unresolved_repo_import("def broken(:", tmp_path) is None


def test_unknown_language_repairs_only_the_unambiguous_single_line_case():
    collapsed = "public void t() {\\n    assertTrue(true);\\n}"
    assert "\\n" not in normalize_generated_code(collapsed, "java")

    # Real multi-line source keeps any escapes it legitimately contains.
    multiline = 'public void t() {\n    assertEquals("a\\nb", x);\n}'
    assert normalize_generated_code(multiline, "java") == multiline.strip()
