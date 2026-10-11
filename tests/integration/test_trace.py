import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from opsmind.agent.runtime import AgentRuntime
from opsmind.api.agent import get_store
from opsmind.api.dependencies import get_demo_actor
from opsmind.core.config import Settings
from opsmind.llm.client import OpenAICompatibleClient
from opsmind.main import create_app
from opsmind.observability.trace import build_trace
from tests.integration.test_agent import ACTOR, CREATE, ScriptedModel, call, final
from tests.integration.test_agent import store as store

pytestmark = pytest.mark.integration


def test_http_usage_reaches_trace(store):
    async def execute():
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Done"},
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenAICompatibleClient(
                Settings(_env_file=None, llm_api_key="synthetic-secret"), http
            )
            return await AgentRuntime(store, client).create("private-user-message", ACTOR)

    run = asyncio.run(execute())
    trace = build_trace(run)
    assert trace["metrics"]["token_usage"]["total_tokens"] == 10
    assert "synthetic-secret" not in json.dumps(trace) and "private-user-message" not in json.dumps(
        trace
    )


def test_failed_model_is_timed_with_unknown_usage(store):
    from opsmind.evaluation.dataset import Step
    from opsmind.evaluation.fixtures import ScriptedClient

    run = asyncio.run(
        AgentRuntime(store, ScriptedClient([Step(error="llm_timeout")])).create("test", ACTOR)
    )
    trace = build_trace(run)
    assert trace["metrics"]["model_errors"] == 1
    assert trace["metrics"]["observed_processing_ms"] >= 1
    assert trace["metrics"]["token_usage"] is None


def test_trace_duplicate_confirmation_does_not_count_again(store):
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE), final()]))
    run = asyncio.run(runtime.create("create", ACTOR))
    done = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    repeated = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    assert build_trace(done)["metrics"] == build_trace(repeated)["metrics"]
    assert build_trace(done)["metrics"]["write_executions"] == 1
    assert build_trace(done)["metrics"]["tool_calls"] == 1
    assert "arguments" not in json.dumps(build_trace(done))


def test_trace_api_owner_and_no_model_invocation(store):
    runtime = AgentRuntime(store, ScriptedModel([final()]))
    run = asyncio.run(runtime.create("private", ACTOR))
    app = create_app(Settings(_env_file=None, database_url=""))
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        response = client.get(f"/api/v1/agent/runs/{run.id}/trace")
        assert response.status_code == 200 and "metrics" in response.json()
        app.dependency_overrides[get_demo_actor] = lambda: "EMP-1002"
        assert client.get(f"/api/v1/agent/runs/{run.id}/trace").status_code == 403


def test_rejected_approval_has_no_write_execution(store):
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)]))
    run = asyncio.run(runtime.create("create", ACTOR))
    rejected = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], False))
    metrics = build_trace(rejected)["metrics"]
    assert metrics["write_executions"] == 0 and metrics["approval_wait_ms"] >= 0


def test_trace_survives_node_replay_without_double_counting(store, monkeypatch):
    from opsmind.agent.nodes import GraphNodes

    original = GraphNodes.apply

    async def crash(self, state):
        await original(self, state)
        raise RuntimeError("injected")

    monkeypatch.setattr(GraphNodes, "apply", crash)
    run = store.create("query", ACTOR)
    with pytest.raises(RuntimeError):
        asyncio.run(
            AgentRuntime(
                store, ScriptedModel([call("get_equipment", {"equipment_no": "EQ-10023"})])
            ).drive(run.id, ACTOR)
        )
    monkeypatch.setattr(GraphNodes, "apply", original)
    done = asyncio.run(AgentRuntime(store, ScriptedModel([final()])).drive(run.id, ACTOR))
    metrics = build_trace(done)["metrics"]
    assert metrics["tool_calls"] == 1 and metrics["model_calls"] == 2
