"""P2 input and validated output, not a verified maintenance diagnosis."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from opsmind.llm.types import TokenUsage

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]


class FaultAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: ShortText
    possible_causes: list[ShortText] = Field(max_length=5)
    missing_information: list[ShortText] = Field(max_length=5)
    suggested_actions: list[ShortText] = Field(min_length=1, max_length=5)
    needs_human_review: bool


class AnalysisResponse(BaseModel):
    analysis: FaultAnalysis
    scope: Literal["user_input_only"] = "user_input_only"
    model: str
    usage: TokenUsage | None
    attempts: int
    latency_ms: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, object]] | None = None


class AnalysisErrorResponse(BaseModel):
    error: ErrorDetail
