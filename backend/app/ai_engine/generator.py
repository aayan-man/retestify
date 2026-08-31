from __future__ import annotations

from app.knowledge_base.schema import Component, TestCase
from app.repo_manager.workspace import Workspace

from .prompts import prompt_builder
from .providers.base import LLMProvider
from .schemas import GeneratedTest
from .structured import complete_structured


def generate_test(
    component: Component, provider: LLMProvider, workspace: Workspace, framework: str
) -> GeneratedTest:
    system, user = prompt_builder.build_generation_prompt(component, workspace.source_dir, framework)
    parsed, _ = complete_structured(provider, system, user, GeneratedTest)
    return parsed


def improve_test(
    component: Component,
    test: TestCase,
    rationale: str,
    provider: LLMProvider,
    workspace: Workspace,
    framework: str,
) -> GeneratedTest:
    system, user = prompt_builder.build_improvement_prompt(
        component, test, workspace.source_dir, framework, rationale
    )
    parsed, _ = complete_structured(provider, system, user, GeneratedTest)
    return parsed
