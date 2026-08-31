from __future__ import annotations

import hashlib
from pathlib import Path

from app.ai_engine.schemas import GeneratedTest
from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .common import insert_method_into_class


def target_test_file(workspace: Workspace, component: Component) -> Path:
    source_path = Path(component.file_path)
    class_name = component.name if component.parent_id else source_path.stem
    test_dir = Path(str(source_path.parent).replace("src/main/java", "src/test/java", 1))
    candidate_dir = workspace.source_dir / test_dir if str(test_dir) != "." else workspace.source_dir / source_path.parent
    return candidate_dir / f"{class_name}Test.java"


def write_generated_test(
    workspace: Workspace, component: Component, generated: GeneratedTest, framework: str
) -> TestCase:
    test_file = target_test_file(workspace, component)
    class_name = test_file.stem
    header = (
        f"import org.junit.Test;\nimport static org.junit.Assert.*;\n\n"
        f"public class {class_name} {{\n"
    )
    code = generated.code.strip()
    if "@Test" not in code:
        code = f"@Test\n{code}"

    start_line, end_line = insert_method_into_class(test_file, code, header)

    rel_path = test_file.relative_to(workspace.source_dir).as_posix()
    body_hash = "sha256:" + hashlib.sha256((code.strip() + "\n").encode("utf-8")).hexdigest()

    return TestCase(
        id=f"java:{rel_path}:{generated.test_name}:{start_line}",
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
