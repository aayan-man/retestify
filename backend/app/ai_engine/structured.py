from __future__ import annotations

from pydantic import BaseModel, ValidationError

from .providers.base import LLMProvider, LLMResponse


def complete_structured(
    provider: LLMProvider,
    system: str,
    user: str,
    schema: type[BaseModel],
    max_attempts: int = 2,
) -> tuple[BaseModel, LLMResponse]:
    """Call the provider and validate its output against `schema`, retrying
    with a corrective follow-up message if the first response doesn't
    parse (providers occasionally fail to honor structured-output mode,
    especially smaller/local models)."""
    messages = [{"role": "user", "content": user}]
    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = provider.complete(messages, system=system, response_schema=schema)
        try:
            if response.raw_json is not None:
                return schema.model_validate(response.raw_json), response
            return schema.model_validate_json(response.text), response
        except ValidationError as e:
            last_error = e
            messages = messages + [
                {"role": "assistant", "content": response.text or "(no text output)"},
                {
                    "role": "user",
                    "content": f"That response did not match the required schema ({e}). "
                    "Respond again using the schema exactly.",
                },
            ]

    raise RuntimeError(f"LLM did not produce a schema-valid response after {max_attempts} attempts: {last_error}")
