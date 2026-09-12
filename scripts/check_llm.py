"""One real synthetic request, no automatic retries. Never prints the API key."""

import asyncio

import httpx

from opsmind.core.config import Settings
from opsmind.llm.client import OpenAICompatibleClient
from opsmind.llm.errors import LLMError
from opsmind.schemas.analysis import AnalysisRequest
from opsmind.services.analysis import analyze_description


async def main() -> None:
    settings = Settings().model_copy(update={"llm_max_retries": 0})
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        try:
            result = await analyze_description(
                AnalysisRequest(description="演示设备 EQ-DEMO 开机后报警，没有报警码和测量信息。"),
                OpenAICompatibleClient(settings, http),
            )
        except LLMError as exc:
            print(f"Model check failed: {exc.code}. {exc.message}")
            raise SystemExit(1) from None
    # Only the synthetic example output is printed, not real enterprise data.
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
