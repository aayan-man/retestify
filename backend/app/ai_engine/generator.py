from __future__ import annotations

from collections.abc import Callable

from app.knowledge_base.schema import Component, TestCase
from app.personalization.profile import CompanyProfile
from app.repo_manager.workspace import Workspace

from .code_validation import GeneratedCodeError, normalize_generated_code, unresolved_repo_import
from .prompts import prompt_builder
from .providers.base import LLMProvider
from .schemas import GeneratedTest
from .structured import complete_structured


def _code_validator(component: Component, workspace: Workspace) -> Callable[[GeneratedTest], GeneratedTest]:
    """Reject or repair a generated test before it can be written to disk."""

    def validate(parsed: GeneratedTest) -> GeneratedTest:
        code = normalize_generated_code(parsed.code, component.language)
        if component.language == "python":
            bad_import = unresolved_repo_import(code, workspace.source_dir)
            if bad_import is not None:
                raise GeneratedCodeError(bad_import)
        return parsed.model_copy(update={"code": code})

    return validate


def generate_test(
    component: Component,
    provider: LLMProvider,
    workspace: Workspace,
    framework: str,
    company_profile: CompanyProfile | None = None,
) -> GeneratedTest:
    style_guide = company_profile.style_guide if company_profile else None
    system, user = prompt_builder.build_generation_prompt(component, workspace.source_dir, framework, style_guide)
    parsed, _ = complete_structured(
        provider, system, user, GeneratedTest, postprocess=_code_validator(component, workspace)
    )
    return parsed


def improve_test(
    component: Component,
    test: TestCase,
    rationale: str,
    provider: LLMProvider,
    workspace: Workspace,
    framework: str,
    company_profile: CompanyProfile | None = None,
) -> GeneratedTest:
    style_guide = company_profile.style_guide if company_profile else None
    system, user = prompt_builder.build_improvement_prompt(
        component, test, workspace.source_dir, framework, rationale, style_guide
    )
    parsed, _ = complete_structured(
        provider, system, user, GeneratedTest, postprocess=_code_validator(component, workspace)
    )
    return parsed
