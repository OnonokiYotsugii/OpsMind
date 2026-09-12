"""No database/tool dependencies: parse and validate preliminary model output."""

import logging

from pydantic import ValidationError

from opsmind.llm.errors import LLMError
from opsmind.llm.prompts import PROMPT_VERSION, build_messages
from opsmind.llm.types import JSONClient
from opsmind.schemas.analysis import AnalysisRequest, AnalysisResponse, FaultAnalysis

logger = logging.getLogger("opsmind.analysis")


async def analyze_description(data: AnalysisRequest, client: JSONClient) -> AnalysisResponse:
    completion = await client.complete_json(build_messages(data.description))
    try:
        analysis = FaultAnalysis.model_validate_json(completion.content, strict=True)
    except ValidationError:
        # Do not log the model content or validation exception (they contain user data).
        raise LLMError(
            "llm_invalid_output",
            "Model output did not match the required analysis structure.",
        ) from None
    logger.info(
        "analysis_completed prompt_version=%s attempts=%d latency_ms=%d",
        PROMPT_VERSION,
        completion.attempts,
        completion.latency_ms,
    )
    return AnalysisResponse(
        analysis=analysis,
        model=completion.model,
        usage=completion.usage,
        attempts=completion.attempts,
        latency_ms=completion.latency_ms,
    )
