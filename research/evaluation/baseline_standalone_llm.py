from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.ai_engine.providers.base import LLMProvider
from app.ai_engine.structured import complete_structured
from app.analyzers.registry import detect_all
from app.jobs import pipeline

from .cost_tracking import CostTrackingProvider
from .metrics import RunMetrics

_SYSTEM = "You are an expert test engineer."
_PROMPT_TEMPLATE = (
    "Write a complete {framework} test file for the following source file. "
    "Include tests for its public functions/classes, including at least one edge case. "
    "Respond with the full test file content only.\n\n"
    "File: {file_path}\n\n```\n{source}\n```\n"
)


class StandaloneGeneratedTests(BaseModel):
    test_code: str = Field(description="Complete test file content for the given source file.")


def run_standalone_llm_baseline(
    provider: LLMProvider,
    repo_path: str | None = None,
    github_url: str | None = None,
    framework: str = "pytest",
) -> RunMetrics:
    """The 'standalone LLM' comparison arm: ask the LLM to generate tests
    directly from raw file content, with NO static-analysis context and no
    source-test mapping — this isolates whether the framework's
    knowledge-base context actually helps, versus a bare generation prompt.

    Scope note: unlike the framework's own generation path, this baseline
    does not write generated tests to disk or execute them — coverage
    before/after is intentionally left unset here; test_count is a proxy
    (files a test file was successfully generated for), not an individual
    test-function count.
    """
    tracked = CostTrackingProvider(provider)
    start = time.monotonic()

    workspace = pipeline.ingest_source(path=repo_path, github_url=github_url)
    summary = pipeline.analyze(workspace)

    generated_files = 0
    for analyzer in detect_all(workspace):
        for file_path in analyzer.list_source_files(workspace):
            if analyzer.is_test_file(file_path):
                continue
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            prompt = _PROMPT_TEMPLATE.format(framework=framework, file_path=file_path.name, source=source[:6000])
            try:
                complete_structured(tracked, _SYSTEM, prompt, StandaloneGeneratedTests, max_attempts=1)
                generated_files += 1
            except Exception:
                continue  # one file's generation failing shouldn't abort the whole baseline run

    elapsed = time.monotonic() - start
    return RunMetrics(
        repo=github_url or repo_path or "unknown",
        variant="standalone_llm_baseline",
        execution_time_s=elapsed,
        component_count=summary.component_count,
        test_count=generated_files,
        mapped_test_count=0,  # no source-test mapping concept for this baseline
        recommendations_count=generated_files,
        total_input_tokens=tracked.total_input_tokens,
        total_output_tokens=tracked.total_output_tokens,
    )
