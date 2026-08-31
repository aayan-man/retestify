from __future__ import annotations

from app.knowledge_base.schema import Component, TestCase
from app.personalization.profile import CompanyProfile
from app.repo_manager.workspace import Workspace

from .prompts import prompt_builder
from .providers.base import LLMProvider
from .schemas import GeneratedTest
from .structured import complete_structured


def generate_test(
    component: Component,
    provider: LLMProvider,
    workspace: Workspace,
    framework: str,
    company_profile: CompanyProfile | None = None,
) -> GeneratedTest:
    style_guide = company_profile.style_guide if company_profile else None
    system, user = prompt_builder.build_generation_prompt(component, workspace.source_dir, framework, style_guide)
    parsed, _ = complete_structured(provider, system, user, GeneratedTest)
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
    parsed, _ = complete_structured(provider, system, user, GeneratedTest)
    return parsed
