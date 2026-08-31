from __future__ import annotations

import hashlib
from pathlib import Path

from app.ai_engine.schemas import GeneratedTest
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .common import append_test_block


def target_test_file(workspace: Workspace, component: Component) -> Path:
    source_path = Path(component.file_path)
    ext = source_path.suffix.lstrip(".") or "cpp"
    candidates = [
        workspace.source_dir / source_path.parent / f"{source_path.stem}_test.{ext}",
        workspace.source_dir / "tests" / f"{source_path.stem}_test.{ext}",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def write_generated_test(
    workspace: Workspace, component: Component, generated: GeneratedTest, framework: str
) -> TestCase:
    # GoogleTest/Catch2 tests are free-standing TEST(...)/TEST_CASE(...)
    # blocks, so the same append-to-file convention used for pytest/Jest
    # works here too — no enclosing class needed.
    test_file = target_test_file(workspace, component)
    start_line, end_line = append_test_block(test_file, generated.code)

    rel_path = test_file.relative_to(workspace.source_dir).as_posix()
    body_hash = "sha256:" + hashlib.sha256((generated.code.strip() + "\n").encode("utf-8")).hexdigest()

    return TestCase(
        id=f"cpp:{rel_path}:{generated.test_name}:{start_line}",
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
