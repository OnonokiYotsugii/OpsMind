"""Tool-call envelope parsing. P3 intentionally accepts one tool per model turn."""

import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opsmind.llm.errors import LLMError


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$")
    arguments: str = Field(max_length=16000)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    index: int | None = Field(default=None, ge=0)
    id: str = Field(min_length=1, max_length=128)
    type: str = Field(pattern="^function$")
    function: FunctionCall


@dataclass(frozen=True)
class ToolTurn:
    message: dict
    call: ToolCall | None


class ToolClient(Protocol):
    async def complete_tools(self, messages: list[dict], tools: list[dict]) -> ToolTurn: ...


def decode_tool_turn(raw: bytes) -> ToolTurn:
    try:
        body = json.loads(raw)
        choice = body["choices"][0]
        msg = choice["message"]
        if msg.get("refusal") or msg.get("role") != "assistant":
            raise ValueError("Not an assistant response.")
        if choice["finish_reason"] == "tool_calls":
            calls = msg["tool_calls"]
            if isinstance(calls, list) and len(calls) > 1:
                raise LLMError("llm_multiple_tool_calls", "Choose one tool per turn.")
            if not isinstance(calls, list) or len(calls) != 1:
                raise ValueError("Exactly one tool call per turn is supported.")
            call = ToolCall.model_validate(calls[0])
            return ToolTurn(
                message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [call.model_dump(exclude={"index"})],
                },
                call=call,
            )
        content = msg.get("content")
        if choice["finish_reason"] != "stop" or msg.get("tool_calls"):
            raise ValueError("Incomplete model response.")
        if not isinstance(content, str) or not content.strip() or len(content) > 12000:
            raise ValueError("Empty or oversized response.")
        return ToolTurn(message={"role": "assistant", "content": content}, call=None)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ValidationError):
        raise LLMError(
            "llm_invalid_tool_response",
            "Expected a final answer or one valid tool call.",
        ) from None
