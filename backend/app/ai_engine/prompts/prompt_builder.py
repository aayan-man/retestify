from __future__ import annotations

from pathlib import Path
from string import Template

from app.knowledge_base.schema import Component, TestCase

_TEMPLATE_DIR = Path(__file__).parent
_SYSTEM_PROMPT = "You are an expert test engineer. Always respond using the provided tool/schema."


def _load(name: str) -> Template:
    return Template((_TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def _read_snippet(root: Path, file_path: str, line_start: int, line_end: int) -> str:
    try:
        lines = (root / file_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return "<source unavailable>"
    return "\n".join(lines[line_start - 1 : line_end])


def build_classification_prompt(
    component: Component,
    tests: list[TestCase],
    source_root: Path,
    change_summary: str | None = None,
) -> tuple[str, str]:
    tests_block = (
        "\n\n".join(
            f"--- {t.name} ({t.file_path}:{t.line_start}) ---\n"
            + _read_snippet(source_root, t.file_path, t.line_start, t.line_end)
            for t in tests
        )
        or "(none)"
    )
    prompt = _load("classify_test.txt").substitute(
        language=component.language,
        component_name=component.name,
        component_kind=component.kind,
        component_file=component.file_path,
        component_signature=component.signature or "",
        component_docstring=component.docstring or "(none)",
        component_complexity=component.metrics.cyclomatic_complexity,
        component_source=_read_snippet(source_root, component.file_path, component.line_start, component.line_end),
        tests_block=tests_block,
        change_context=f"Recent change: {change_summary}" if change_summary else "",
    )
    return _SYSTEM_PROMPT, prompt


def _system_prompt(style_guide: str | None) -> str:
    if not style_guide:
        return _SYSTEM_PROMPT
    return f"{_SYSTEM_PROMPT}\n\nFollow this organization's testing conventions:\n{style_guide}"


def build_generation_prompt(
    component: Component, source_root: Path, framework: str, style_guide: str | None = None
) -> tuple[str, str]:
    prompt = _load("generate_test.txt").substitute(
        language=component.language,
        framework=framework,
        component_name=component.name,
        component_kind=component.kind,
        component_file=component.file_path,
        component_signature=component.signature or "",
        component_docstring=component.docstring or "(none)",
        component_source=_read_snippet(source_root, component.file_path, component.line_start, component.line_end),
    )
    return _system_prompt(style_guide), prompt


def build_improvement_prompt(
    component: Component,
    test: TestCase,
    source_root: Path,
    framework: str,
    rationale: str,
    style_guide: str | None = None,
) -> tuple[str, str]:
    prompt = _load("improve_test.txt").substitute(
        language=component.language,
        framework=framework,
        component_name=component.name,
        component_file=component.file_path,
        component_source=_read_snippet(source_root, component.file_path, component.line_start, component.line_end),
        test_name=test.name,
        test_source=_read_snippet(source_root, test.file_path, test.line_start, test.line_end),
        rationale=rationale,
    )
    return _system_prompt(style_guide), prompt
