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
