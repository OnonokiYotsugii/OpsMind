import asyncio
import copy
import json

import httpx
import pytest

from opsmind.llm.client import MAX_RESPONSE_BYTES, OpenAICompatibleClient
from opsmind.llm.errors import LLMError


async def no_sleep(_seconds):
    pass


def run_client(settings, handler, sleep=no_sleep):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await OpenAICompatibleClient(settings, http, sleep).complete_json(
                [
                    {"role": "user", "content": "synthetic JSON input"},
                ]
            )

    return asyncio.run(run())


def test_success_payload_and_metadata(llm_settings, envelope):
    def handler(request):
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key-not-real"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-pro"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is False
        assert "tools" not in payload
        return httpx.Response(200, json=envelope)

    result = run_client(llm_settings, handler)
    assert result.attempts == 1
    assert result.usage.total_tokens == 180
    assert result.latency_ms >= 0


def test_generic_provider_omits_deepseek_option(llm_settings, envelope):
    settings = llm_settings.model_copy(
        update={
            "llm_provider": "openai_compatible",
            "llm_base_url": "https://example.com/v1",
        }
    )

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert "thinking" not in json.loads(request.content)
        return httpx.Response(200, json=envelope)

    run_client(settings, handler)


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "llm_request_rejected"),
        (401, "llm_authentication_failed"),
        (403, "llm_authentication_failed"),
        (402, "llm_balance_unavailable"),
        (404, "llm_request_rejected"),
        (302, "llm_request_rejected"),
    ],
)
def test_permanent_errors_do_not_retry_or_expose_body(llm_settings, status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="private upstream body and key",
            headers={
                "Location": "https://untrusted.example/",
            },
        )

    with pytest.raises(LLMError) as caught:
        run_client(llm_settings, handler)
    assert caught.value.code == code
    assert "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_failure_then_success(llm_settings, envelope, status):
    calls = []
    delays = []

    async def record_sleep(seconds):
        delays.append(seconds)

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(status, headers={"Retry-After": "0.01"})
            if len(calls) == 1
            else httpx.Response(200, json=envelope)
        )

    result = run_client(llm_settings, handler, record_sleep)
    assert result.attempts == 2
    assert delays == [0.01]


def test_retry_limit(llm_settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    with pytest.raises(LLMError, match="temporarily unavailable") as caught:
        run_client(llm_settings, handler)
    assert caught.value.code == "llm_rate_limited"
    assert len(calls) == 2


@pytest.mark.parametrize(
    "exception,code,status",
    [
        (httpx.ReadTimeout, "llm_timeout", 504),
        (httpx.ConnectError, "llm_connection_failed", 503),
    ],
)
def test_transport_failures_are_bounded(llm_settings, exception, code, status):
    calls = []

    def handler(request):
        calls.append(request)
        raise exception("secret upstream details", request=request)

    with pytest.raises(LLMError) as caught:
        run_client(llm_settings, handler)
    assert caught.value.code == code
    assert caught.value.status_code == status
    assert len(calls) == 2
    assert "secret" not in str(caught.value)


def test_total_deadline_cancels_pending_request(llm_settings):
    async def handler(_request):
        await asyncio.sleep(10)
        return httpx.Response(200)

    with pytest.raises(LLMError) as caught:
        run_client(llm_settings.model_copy(update={"llm_total_timeout_seconds": 0.01}), handler)
    assert caught.value.code == "llm_timeout"


@pytest.mark.parametrize(
    "change,code",
    [
        ({"finish_reason": "length"}, "llm_output_truncated"),
        ({"finish_reason": "content_filter"}, "llm_incomplete_response"),
        ({"message": {"content": ""}}, "llm_empty_response"),
        ({"message": {"content": "   "}}, "llm_empty_response"),
        ({"message": {"content": None}}, "llm_empty_response"),
        (
            {"message": {"content": "{}", "tool_calls": [{"name": "create_ticket"}]}},
            "llm_incomplete_response",
        ),
    ],
)
def test_invalid_completions_not_retried(llm_settings, envelope, change, code):
    body = copy.deepcopy(envelope)
    body["choices"][0].update(change)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    with pytest.raises(LLMError) as caught:
        run_client(llm_settings, handler)
    assert caught.value.code == code
    assert len(calls) == 1


@pytest.mark.parametrize("body", [[], {}, {"choices": []}, {"choices": [None]}])
def test_invalid_envelope(llm_settings, body):
    with pytest.raises(LLMError) as caught:
        run_client(llm_settings, lambda _: httpx.Response(200, json=body))
    assert caught.value.code == "llm_invalid_response"


def test_invalid_http_json(llm_settings):
    with pytest.raises(LLMError) as caught:
        run_client(llm_settings, lambda _: httpx.Response(200, content=b"not json"))
    assert caught.value.code == "llm_invalid_response"


def test_response_size_limit(llm_settings):
    with pytest.raises(LLMError) as caught:
        run_client(
            llm_settings,
            lambda _: httpx.Response(
                200,
                content=b"x" * (MAX_RESPONSE_BYTES + 1),
            ),
        )
    assert caught.value.code == "llm_response_too_large"


def test_usage_may_be_absent(llm_settings, envelope):
    envelope.pop("usage")
    assert run_client(llm_settings, lambda _: httpx.Response(200, json=envelope)).usage is None
