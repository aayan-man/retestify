from pathlib import Path

from app.analyzers.base import LanguageAnalyzer
from app.knowledge_base.schema import TestCase
from app.repo_manager.workspace import Workspace


def find_test_files(workspace: Workspace, analyzer: LanguageAnalyzer) -> list[Path]:
    return [f for f in analyzer.list_source_files(workspace) if analyzer.is_test_file(f)]


def extract_test_cases(
    workspace: Workspace, analyzer: LanguageAnalyzer, project_id: str, framework: str
) -> list[TestCase]:
    test_cases: list[TestCase] = []
    for file_path in find_test_files(workspace, analyzer):
        test_cases.extend(
            analyzer.list_test_cases(file_path, project_id=project_id, root=workspace.source_dir, framework=framework)
        )
    return test_cases
