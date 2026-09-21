import pytest

from app.ai_engine.code_validation import GeneratedCodeError, normalize_generated_code
from app.ai_engine.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.ai_engine.schemas import GeneratedTest
from app.ai_engine.structured import complete_structured


class ScriptedProvider(LLMProvider):
    """Returns each canned payload in turn, recording what it was sent."""

    name = "scripted"

    def __init__(self, *responses: dict):
        self.responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        response_schema=None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            text="", raw_json=self.responses[len(self.calls) - 1], model="scripted-model", provider=self.name
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def _validator(parsed: GeneratedTest) -> GeneratedTest:
    return parsed.model_copy(update={"code": normalize_generated_code(parsed.code, "python")})


def _payload(code: str) -> dict:
    return {"test_name": "test_thing", "code": code, "rationale": "why", "confidence": 0.9}


def test_unparseable_code_triggers_a_corrective_retry():
    provider = ScriptedProvider(
        _payload("def test_thing(:\n    assert True"),
        _payload("def test_thing():\n    assert True"),
    )

    parsed, _ = complete_structured(
        provider, "sys", "user", GeneratedTest, postprocess=_validator
    )

    assert len(provider.calls) == 2, "a rejected generation should be retried, not accepted"
    assert parsed.code == "def test_thing():\n    assert True"
    # The retry has to tell the model what was wrong with the first attempt.
    assert "rejected" in provider.calls[1][-1]["content"]


def test_code_that_stays_invalid_raises_rather_than_returning_broken_source():
    provider = ScriptedProvider(
        _payload("def test_thing(:\n    assert True"),
        _payload("still not valid ("),
    )

    with pytest.raises(RuntimeError, match="did not produce a valid response"):
        complete_structured(provider, "sys", "user", GeneratedTest, postprocess=_validator)


def test_valid_code_is_accepted_on_the_first_call():
    provider = ScriptedProvider(_payload("def test_thing():\n    assert True"))

    parsed, _ = complete_structured(
        provider, "sys", "user", GeneratedTest, postprocess=_validator
    )

    assert len(provider.calls) == 1
    assert parsed.test_name == "test_thing"


def test_postprocess_is_optional_so_other_schemas_are_unaffected():
    provider = ScriptedProvider(_payload("anything at all ((("))

    parsed, _ = complete_structured(provider, "sys", "user", GeneratedTest)

    assert parsed.code == "anything at all ((("


def test_normalize_is_what_rejects_the_bad_code():
    """Guards the seam: the retry above only happens because the validator
    raises, so assert that directly too."""
    with pytest.raises(GeneratedCodeError):
        normalize_generated_code("def test_thing(:", "python")
