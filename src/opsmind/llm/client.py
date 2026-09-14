"""Bounded async Chat Completions adapter; provider options stay inside this layer."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

import httpx

from opsmind.core.config import Settings
from opsmind.llm.errors import LLMError
from opsmind.llm.protocol import decode_completion
from opsmind.llm.tool_protocol import ToolTurn, decode_tool_turn
from opsmind.llm.types import Completion

logger = logging.getLogger("opsmind.llm")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RESPONSE_BYTES = 256_000


class OpenAICompatibleClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.settings = settings
        self.http = http
        self.sleep = sleep

    def payload(self, messages: list[dict[str, str]]) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.llm_max_output_tokens,
            "stream": False,
        }
        if self.settings.llm_provider == "deepseek":
            # P2 uses non-thinking mode to keep output and latency bounded.
            payload["thinking"] = {"type": "disabled"}
        return payload

    async def complete_json(self, messages: list[dict[str, str]]) -> Completion:
        if not self.settings.llm_api_key.get_secret_value().strip():
            raise LLMError("llm_not_configured", "Configure the model API key locally first.", 503)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.llm_total_timeout_seconds):
                return await self._attempts(messages, started)
        except TimeoutError:
            raise LLMError(
                "llm_timeout", "Model request exceeded its total time budget.", 504
            ) from None

    async def complete_tools(self, messages: list[dict], tools: list[dict]) -> ToolTurn:
        if not self.settings.llm_api_key.get_secret_value().strip():
            raise LLMError("llm_not_configured", "Configure the model API key locally first.", 503)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.llm_total_timeout_seconds):
                return await self._attempts(messages, started, tools=tools)
        except TimeoutError:
            raise LLMError("llm_timeout", "Model request exceeded its time budget.", 504) from None

    async def _attempts(
        self,
        messages: list[dict],
        started: float,
        tools: list[dict] | None = None,
    ) -> Completion | ToolTurn:
        attempts = self.settings.llm_max_retries + 1
        endpoint = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        payload = self.payload(messages)
        if tools is not None:
            payload.pop("response_format", None)
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        for index in range(attempts):
            retry_after: str | None = None
            try:
                async with self.http.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.settings.llm_timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    if response.status_code == 200:
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_RESPONSE_BYTES:
                                raise LLMError(
                                    "llm_response_too_large", "Model response is too large."
                                )
                        if tools is not None:
                            return decode_tool_turn(bytes(raw))
                        content, model, usage = decode_completion(bytes(raw))
                        return Completion(
                            content=content,
                            model=model,
                            usage=usage,
                            attempts=index + 1,
                            latency_ms=round((time.monotonic() - started) * 1000),
                        )
                    status = response.status_code
                    if status in {401, 403}:
                        raise LLMError(
                            "llm_authentication_failed",
                            "Model credentials or access were rejected.",
                            503,
                        )
                    if status == 402:
                        raise LLMError(
                            "llm_balance_unavailable", "Model account balance unavailable.", 503
                        )
                    if status not in RETRYABLE_STATUS:
                        raise LLMError(
                            "llm_request_rejected", "Model service rejected this request."
                        )
                    retry_after = response.headers.get("Retry-After")
                    failure = LLMError(
                        "llm_rate_limited" if status == 429 else "llm_unavailable",
                        "Model service is temporarily unavailable.",
                        503,
                    )
            except httpx.TimeoutException:
                failure = LLMError("llm_timeout", "Model request timed out.", 504)
            except httpx.TransportError:
                failure = LLMError("llm_connection_failed", "Cannot reach the model service.", 503)
            if index + 1 == attempts:
                raise failure from None
            logger.warning("model_request_retry attempt=%d code=%s", index + 1, failure.code)
            await self.sleep(self._delay(index, retry_after))
        raise AssertionError("Attempt loop must return or raise.")

    @staticmethod
    def _delay(index: int, retry_after: str | None) -> float:
        # Honor numeric retry hints up to 5s; exponential backoff otherwise.
        if retry_after:
            try:
                delay = float(retry_after)
                if 0 <= delay <= 5:
                    return delay
            except ValueError:
                pass
        return min(0.5 * 2**index + random.uniform(0, 0.25), 5.0)
