"""Validate the upstream envelope separately from business output."""

import json

from pydantic import ValidationError

from opsmind.llm.errors import LLMError
from opsmind.llm.types import TokenUsage


def decode_completion(raw: bytes) -> tuple[str, str, TokenUsage | None]:
    try:
        envelope = json.loads(raw)
        choice = envelope["choices"][0]
        reason = choice["finish_reason"]
        if reason == "length":
            raise LLMError("llm_output_truncated", "Model output reached its token limit.")
        if reason != "stop":
            raise LLMError("llm_incomplete_response", "Model did not finish a normal response.")
        message = choice["message"]
        if message.get("tool_calls") or message.get("refusal"):
            raise LLMError("llm_incomplete_response", "Model did not return an analysis.")
        content = message["content"]
        model = envelope["model"]
        if not isinstance(content, str) or not content.strip():
            raise LLMError("llm_empty_response", "Model returned empty content.")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Invalid model identifier.")
        usage = (
            TokenUsage.model_validate(envelope["usage"])
            if envelope.get("usage") is not None
            else None
        )
        return content, model, usage
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ValidationError):
        raise LLMError(
            "llm_invalid_response", "Model service returned an invalid response."
        ) from None
