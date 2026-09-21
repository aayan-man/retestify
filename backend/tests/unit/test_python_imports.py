import ast

from app.test_writer.python_imports import strip_redundant_imports

EXISTING = "import pytest\nimport six\n\n\ndef test_existing():\n    assert six\n"


def test_import_the_file_already_has_is_dropped():
    code = "import pytest\n\ndef test_new():\n    assert True\n"

    result = strip_redundant_imports(code, EXISTING)

    assert "import pytest" not in result
    assert "def test_new():" in result


def test_import_the_file_lacks_is_kept():
    code = "import types\n\ndef test_new():\n    assert types\n"
    assert "import types" in strip_redundant_imports(code, EXISTING)


def test_a_block_repeating_an_import_keeps_only_the_first():
    code = "import types\nimport types\n\ndef test_new():\n    assert types\n"

    result = strip_redundant_imports(code, EXISTING)

    assert result.count("import types") == 1


def test_from_imports_are_distinguished_by_name():
    """`from six import moves` must not be considered covered just because
    `from six import ensure_str` is already present."""
    existing = "from six import ensure_str\n"

    assert "ensure_str" not in strip_redundant_imports("from six import ensure_str\n", existing)
    assert "moves" in strip_redundant_imports("from six import moves\n", existing)


def test_aliases_are_distinguished():
    existing = "import numpy\n"
    assert "as np" in strip_redundant_imports("import numpy as np\n", existing)


def test_partially_new_import_is_kept_whole():
    """Dropping only the covered half would need the statement rewritten;
    keeping it re-imports one name, which is harmless, and never loses one."""
    existing = "from six import ensure_str\n"

    result = strip_redundant_imports("from six import ensure_str, ensure_text\n", existing)

    assert "ensure_text" in result and "ensure_str" in result


def test_future_import_is_always_dropped():
    """It is only legal at the top of a file, so appending one mid-file
    would be a SyntaxError."""
    code = "from __future__ import annotations\nimport types\n\ndef test_new():\n    assert types\n"

    result = strip_redundant_imports(code, "")

    assert "__future__" not in result
    assert "import types" in result


def test_scoped_imports_are_left_alone():
    """An import inside a function or a TYPE_CHECKING block is scoped —
    removing it would change behavior, not just tidy up."""
    code = (
        "def test_new():\n"
        "    import pytest\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError\n"
    )

    assert "import pytest" in strip_redundant_imports(code, EXISTING)


def test_comments_and_formatting_inside_the_test_survive():
    code = (
        "import pytest\n"
        "\n"
        "def test_new():\n"
        "    # this comment must survive\n"
        "    value = {'a': 1}\n"
        "    assert value['a'] == 1\n"
    )

    result = strip_redundant_imports(code, EXISTING)

    assert "# this comment must survive" in result
    assert "value = {'a': 1}" in result


def test_result_is_still_valid_python():
    code = "import pytest\nimport six\n\ndef test_new():\n    assert True\n"
    ast.parse(strip_redundant_imports(code, EXISTING))


def test_unparseable_code_is_returned_untouched():
    broken = "def test_new(:"
    assert strip_redundant_imports(broken, EXISTING) == broken


def test_unparseable_target_file_strips_nothing():
    """A file we can't read shouldn't cause imports to be dropped on the
    assumption they're already there."""
    assert "import pytest" in strip_redundant_imports("import pytest\n", "def broken(:")
