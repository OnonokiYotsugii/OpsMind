from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    usage: TokenUsage | None
    attempts: int
    latency_ms: int


class JSONClient(Protocol):
    async def complete_json(self, messages: list[dict[str, str]]) -> Completion: ...
