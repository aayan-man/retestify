from __future__ import annotations

import hashlib
from pathlib import Path

from app.ai_engine.schemas import GeneratedTest
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .common import append_test_block
from .python_imports import strip_redundant_imports


def target_test_file(workspace: Workspace, component: Component) -> Path:
    """Convention: reuse an existing tests/test_<module>.py (in a top-level
    tests/ dir, or alongside the source file) if one exists for this
    component's module; otherwise create one under tests/."""
    source_path = Path(component.file_path)
    stem = source_path.stem
    candidates = [
        workspace.source_dir / "tests" / f"test_{stem}.py",
        workspace.source_dir / source_path.parent / f"test_{stem}.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def write_generated_test(
    workspace: Workspace, component: Component, generated: GeneratedTest, framework: str
) -> TestCase:
    """Append the AI-generated test function to the conventional test file,
    creating it if needed, and return the TestCase record for it.

    The generated code is expected to include any imports it needs (the
    generation prompt asks for this), so imports the target file already
    has are stripped before appending — otherwise a file accumulates one
    `import pytest` per generated test.
    """
    test_file = target_test_file(workspace, component)
    existing = test_file.read_text(encoding="utf-8") if test_file.exists() else ""
    code = strip_redundant_imports(generated.code, existing)
    start_line, end_line = append_test_block(test_file, code)

    rel_path = test_file.relative_to(workspace.source_dir).as_posix()
    # Hash what was actually written, not the model's raw suggestion, so the
    # record matches the file on disk.
    body_hash = "sha256:" + hashlib.sha256((code.strip() + "\n").encode("utf-8")).hexdigest()

    return TestCase(
        id=f"py:{rel_path}:{generated.test_name}:{start_line}",
        project_id=component.project_id,
        language=component.language,
        framework=framework,
        name=generated.test_name,
        file_path=rel_path,
        line_start=start_line,
        line_end=end_line,
        target_component_ids=[component.id],
        mapping_method="naming_convention",
        mapping_confidence=1.0,
        content_hash=body_hash,
        origin="ai_generated",
    )
