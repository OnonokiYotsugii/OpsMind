import asyncio
import json

import httpx
import pytest

from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.llm.client import OpenAICompatibleClient
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import decode_tool_turn
from opsmind.tools.registry import TOOLS, Risk, validate_call


def tool_response():
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "get_equipment",
                                "arguments": '{"equipment_no":"EQ-10023"}',
                            },
                        }
                    ],
                },
            }
        ]
    }


def test_tools_http_roundtrip_and_non_json_mode():
    async def run():
        def handler(request):
            body = json.loads(request.content)
            assert "response_format" not in body
            assert body["tool_choice"] == "auto"
            assert len(body["tools"]) == 6
            assert body["thinking"] == {"type": "disabled"}
            return httpx.Response(200, json=tool_response())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            settings = Settings(_env_file=None, llm_api_key="synthetic-key")
            turn = await OpenAICompatibleClient(settings, http).complete_tools(
                [{"role": "user", "content": "查询设备"}],
                [t.declaration() for t in TOOLS.values()],
            )
            assert turn.call.function.name == "get_equipment"

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["multiple", "empty", "length", "wrong_role", "bad_args_type"])
def test_malformed_tool_response_rejected(mode):
    body = tool_response()
    choice = body["choices"][0]
    if mode == "multiple":
        choice["message"]["tool_calls"] *= 2
    elif mode == "empty":
        choice["message"]["tool_calls"] = []
    elif mode == "length":
        choice["finish_reason"] = "length"
    elif mode == "wrong_role":
        choice["message"]["role"] = "user"
    else:
        choice["message"]["tool_calls"][0]["function"]["arguments"] = {}
    with pytest.raises(LLMError):
        decode_tool_turn(json.dumps(body).encode())


@pytest.mark.parametrize(
    "name,args",
    [
        ("execute_shell", "{}"),
        ("get_equipment", '{"equipment_no":"EQ-1","approved":true}'),
        ("get_equipment", '{"equipment_no":"EQ-1","equipment_no":"EQ-2"}'),
        ("get_maintenance_history", '{"equipment_no":"EQ-1","limit":100}'),
        ("get_ticket_history", '{"equipment_no":"EQ-1","limit":true}'),
        ("create_ticket", '{"created_by":1}'),
        ("update_ticket", '{"ticket_no":"TK-1","changes":{}}'),
    ],
)
def test_tool_whitelist_and_arguments(name, args):
    with pytest.raises(BusinessError):
        validate_call(name, args)


def test_risk_is_server_owned():
    assert TOOLS["create_ticket"].risk == Risk.MEDIUM
    assert TOOLS["update_ticket"].risk == Risk.HIGH
    assert all(t.risk == Risk.LOW for n, t in TOOLS.items() if n.startswith("get_"))


def test_deepseek_index_metadata_is_accepted_and_not_echoed():
    body = tool_response()
    body["choices"][0]["message"]["tool_calls"][0]["index"] = 0
    turn = decode_tool_turn(json.dumps(body).encode())
    assert turn.call.function.name == "get_equipment"
    assert "index" not in turn.message["tool_calls"][0]


def test_unknown_tool_envelope_fields_still_rejected():
    body = tool_response()
    body["choices"][0]["message"]["tool_calls"][0]["approved"] = True
    with pytest.raises(LLMError):
        decode_tool_turn(json.dumps(body).encode())


def test_write_summary_is_based_on_receipt():
    from opsmind.agent.state import write_receipt_summary

    receipt = {
        "kind": "decision",
        "approved": True,
        "ok": True,
        "tool": "create_ticket",
        "result": {"data": {"ticket_no": "TK-TEST"}},
    }
    summary = write_receipt_summary([receipt])
    assert "已成功执行" in summary and "TK-TEST" in summary
    assert write_receipt_summary([]) is None
