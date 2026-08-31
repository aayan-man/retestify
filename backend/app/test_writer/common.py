from __future__ import annotations

from pathlib import Path


def append_test_block(test_file: Path, code: str) -> tuple[int, int]:
    """Append `code` to `test_file` (creating it and its parent dir if
    needed) and return the 1-indexed (start_line, end_line) it landed on."""
    test_file.parent.mkdir(parents=True, exist_ok=True)
    existing = test_file.read_text(encoding="utf-8") if test_file.exists() else ""
    body = code.strip() + "\n"
    separator = "" if not existing else ("\n\n" if not existing.endswith("\n\n") else "")

    start_line = existing.count("\n") + separator.count("\n") + 1
    end_line = start_line + body.rstrip("\n").count("\n")

    test_file.write_text(existing + separator + body, encoding="utf-8")
    return start_line, end_line


def insert_method_into_class(test_file: Path, method_code: str, class_header: str) -> tuple[int, int]:
    """For languages where a bare test method isn't valid on its own (Java,
    C#): insert the method into an existing test class (just before its
    final closing brace) if the file exists, or create a new file wrapping
    it in `class_header` (expected to end with an opening `{` and newline).
    Returns the 1-indexed (start_line, end_line) the method landed on."""
    test_file.parent.mkdir(parents=True, exist_ok=True)
    method = method_code.strip()
    indented = "\n".join(("    " + line if line.strip() else line) for line in method.splitlines())

    if test_file.exists():
        existing = test_file.read_text(encoding="utf-8")
        insert_at = existing.rfind("}")
        if insert_at != -1:
            prefix = existing[:insert_at]
            suffix = existing[insert_at:]
            new_content = prefix + "\n" + indented + "\n" + suffix
            start_line = prefix.count("\n") + 2
            end_line = start_line + indented.count("\n")
            test_file.write_text(new_content, encoding="utf-8")
            return start_line, end_line

    new_content = class_header + indented + "\n}\n"
    start_line = class_header.count("\n") + 1
    end_line = start_line + indented.count("\n")
    test_file.write_text(new_content, encoding="utf-8")
    return start_line, end_line
