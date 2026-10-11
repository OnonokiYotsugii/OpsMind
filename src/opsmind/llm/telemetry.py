"""Extract numeric metadata only; invalid or absent upstream usage is unknown."""

import re

from pydantic import ValidationError

from opsmind.llm.types import TokenUsage


def response_metadata(body: dict, attempts: int | None = None) -> dict:
    usage = None
    try:
        candidate = TokenUsage.model_validate(body.get("usage"))
        if candidate.prompt_tokens + candidate.completion_tokens == candidate.total_tokens:
            usage = candidate.model_dump()
    except ValidationError:
        pass
    model = body.get("model")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", model):
        model = None
    return {"usage": usage, "model": model, "attempts": attempts}
