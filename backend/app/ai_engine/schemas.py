from typing import Literal

from pydantic import BaseModel, Field


class TestClassification(BaseModel):
    decision: Literal["retain", "modify", "remove"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class GeneratedTest(BaseModel):
    test_name: str
    code: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
