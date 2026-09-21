from __future__ import annotations

import ast

ImportKey = tuple


def _alias_keys(stmt: ast.Import | ast.ImportFrom) -> list[ImportKey]:
    """Identify what each alias in an import statement actually binds, so
    `import six` and `from six import moves` aren't confused for the same
    thing and `import numpy as np` isn't confused with plain `import numpy`."""
    if isinstance(stmt, ast.Import):
        return [("import", alias.name, alias.asname) for alias in stmt.names]
    return [("from", stmt.level, stmt.module or "", alias.name, alias.asname) for alias in stmt.names]


def _module_level_imports(tree: ast.Module) -> list[ast.Import | ast.ImportFrom]:
    # Only top-level statements: an import nested inside a function or an
    # `if TYPE_CHECKING:` block is scoped, and removing it would change
    # behavior rather than just tidy the file.
    return [stmt for stmt in tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom))]


def collect_import_keys(source: str) -> set[ImportKey]:
    """Every name the module level of `source` imports. Unparseable source
    yields nothing, so nothing gets stripped on its account."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    keys: set[ImportKey] = set()
    for stmt in _module_level_imports(tree):
        keys.update(_alias_keys(stmt))
    return keys


def strip_redundant_imports(code: str, existing_source: str) -> str:
    """Remove imports from a generated test block that `existing_source`
    already has, and that the block repeats within itself.

    Each generated test is asked to bring its own imports, and blocks are
    appended to one shared file, so a file accumulated `import pytest`
    twenty-one times. The duplicates are harmless to Python but make the
    result read like machine output rather than a test suite someone would
    keep.

    Lines are dropped from the original text rather than regenerating it
    from the AST, so comments, spacing and formatting inside the test
    survive untouched. A statement is only dropped when *every* name it
    binds is already available; a partially-new import is kept whole,
    which can re-import one name but never loses one.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # invalid code is rejected upstream; don't compound it

    seen = collect_import_keys(existing_source)
    drop_lines: set[int] = set()

    for stmt in _module_level_imports(tree):
        # `from __future__ import ...` is only legal at the very top of a
        # file, so it can never survive being appended to one.
        is_future = isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__"
        keys = _alias_keys(stmt)
        if is_future or all(key in seen for key in keys):
            drop_lines.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
        else:
            seen.update(keys)

    if not drop_lines:
        return code

    kept = [line for number, line in enumerate(code.splitlines(), start=1) if number not in drop_lines]
    return "\n".join(kept).strip("\n")
