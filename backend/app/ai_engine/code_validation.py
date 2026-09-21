from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from pathlib import Path

# Module-level statements that can contain further definitions. Names bound
# inside them are still module attributes, so the collector descends into
# them — six.py, for one, defines much of its API inside `if PY3:` blocks.
_NESTING_STATEMENTS = (ast.If, ast.Try, ast.For, ast.While, ast.With)

# Calls that write straight into a module's namespace. A module doing this
# can bind names no static pass can see, so import checking is skipped for
# it rather than risk rejecting a valid import.
_DYNAMIC_BINDING_MARKERS = ("globals()[", "globals().update(", "vars()[", "sys.modules[__name__]")


class GeneratedCodeError(ValueError):
    """Generated code that isn't usable as source in its target language."""


def _python_syntax_error(code: str) -> str | None:
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"generated Python is not syntactically valid (line {e.lineno}: {e.msg})"
    return None


# Only languages we can cheaply parse in-process are registered. The others
# fall through to the escaped-newline repair below, which is a provider
# artifact rather than anything language-specific.
_SYNTAX_CHECKERS: dict[str, Callable[[str], str | None]] = {
    "python": _python_syntax_error,
}


def _unescape(code: str) -> str:
    return code.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def _looks_single_line_escaped(code: str) -> bool:
    """True for the pathology where a provider emitted "\\n" as two literal
    characters, collapsing a whole test into one unparseable line. Real
    multi-line source never has escaped newlines and no actual ones."""
    return "\\n" in code and "\n" not in code.strip()


def _module_body(node: ast.AST) -> Iterator[ast.stmt]:
    """Yield module-level statements, descending through conditionals and
    loops but never into a function or class body."""
    for stmt in getattr(node, "body", []):
        yield stmt
        if isinstance(stmt, _NESTING_STATEMENTS):
            yield from _module_body(stmt)
            for extra in ("orelse", "finalbody", "handlers"):
                for branch in getattr(stmt, extra, []) or []:
                    if isinstance(branch, ast.stmt):
                        yield branch
                        yield from _module_body(branch)


def _bound_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for stmt in _module_body(tree):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                names.update(_target_names(target))
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            names.update(_target_names(stmt.target))
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {n for el in target.elts for n in _target_names(el)}
    return set()


def _repo_module_file(source_dir: Path, module: str) -> Path | None:
    relative = module.replace(".", "/")
    for candidate in (source_dir / f"{relative}.py", source_dir / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def unresolved_repo_import(code: str, source_dir: Path) -> str | None:
    """Return a message naming a symbol the generated test imports from the
    target repo that doesn't exist there, or None if nothing is provably
    wrong.

    Models sometimes invent a plausible-looking class and import it from the
    module under test, which only fails once the suite is run. Only the
    repo's own modules are checked — third-party and stdlib imports are left
    alone — and anything that can't be resolved with confidence is allowed
    through, since a false rejection costs a component its test.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # syntax is reported separately; nothing to add here

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue  # relative imports don't resolve against source_dir
        module_file = _repo_module_file(source_dir, node.module)
        if module_file is None:
            continue

        try:
            source = module_file.read_text(encoding="utf-8")
            module_tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue
        if any(marker in source for marker in _DYNAMIC_BINDING_MARKERS):
            continue

        available = _bound_names(module_tree)
        for alias in node.names:
            if alias.name != "*" and alias.name not in available:
                return (
                    f"generated test imports '{alias.name}' from '{node.module}', "
                    f"which does not define it"
                )
    return None


def normalize_generated_code(code: str, language: str) -> str:
    """Return `code` in a form that's safe to write into a test file.

    Schema validation only proves `code` is a string — it says nothing
    about whether the string is valid source. Some providers emit "\\n" as
    two literal characters, which produced a single unparseable line and
    broke every test in the file it was appended to, so the text is
    checked here before it can reach disk.

    Raises GeneratedCodeError if the code can't be made valid, which the
    caller turns into a corrective retry.
    """
    candidate = code.strip()
    if not candidate:
        raise GeneratedCodeError("generated code was empty")

    checker = _SYNTAX_CHECKERS.get(language)
    if checker is None:
        # Nothing can be verified for this language, so only the
        # unambiguous escaped-newline case is repaired.
        return _unescape(candidate) if _looks_single_line_escaped(candidate) else candidate

    error = checker(candidate)
    if error is None:
        return candidate

    # Accept the unescaped form only when it demonstrably fixes the parse,
    # so a repair is never applied on a guess.
    if "\\n" in candidate:
        repaired = _unescape(candidate)
        if checker(repaired) is None:
            return repaired

    raise GeneratedCodeError(error)
