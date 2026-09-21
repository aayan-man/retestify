from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from .providers.base import LLMProvider, LLMResponse


def complete_structured(
    provider: LLMProvider,
    system: str,
    user: str,
    schema: type[BaseModel],
    max_attempts: int = 2,
    postprocess: Callable[[BaseModel], BaseModel] | None = None,
) -> tuple[BaseModel, LLMResponse]:
    """Call the provider and validate its output against `schema`, retrying
    with a corrective follow-up message if the first response doesn't
    parse (providers occasionally fail to honor structured-output mode,
    especially smaller/local models).

    `postprocess` runs on the parsed object and may normalize it or raise
    ValueError to reject it. Checks that the schema can't express — such
    as whether a generated code string is valid source — belong there, so
    that they get the same corrective retry as a schema mismatch instead
    of failing outright.
    """
    messages = [{"role": "user", "content": user}]
    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = provider.complete(messages, system=system, response_schema=schema)
        try:
            if response.raw_json is not None:
                parsed = schema.model_validate(response.raw_json)
            else:
                parsed = schema.model_validate_json(response.text)
            # ValidationError subclasses ValueError, so this catches both a
            # schema mismatch and a postprocess rejection.
            return (postprocess(parsed) if postprocess is not None else parsed), response
        except ValueError as e:
            last_error = e
            messages = messages + [
                {"role": "assistant", "content": response.text or "(no text output)"},
                {
                    "role": "user",
                    "content": f"That response was rejected ({e}). Respond again using the "
                    "schema exactly, and make sure any code field contains real source "
                    "with actual newlines, not escaped \\n sequences.",
                },
            ]

    raise RuntimeError(f"LLM did not produce a valid response after {max_attempts} attempts: {last_error}")
