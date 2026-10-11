import asyncio
from datetime import timedelta

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from opsmind.agent.checkpointer import MySQLSaver
from opsmind.agent.execution import run_owner
from opsmind.agent.models import AgentRun
from opsmind.agent.nodes import GraphNodes
from opsmind.agent.runtime import AgentRuntime
from opsmind.core.errors import BusinessError
from opsmind.db.models import utc_now
from tests.integration.test_agent import (
    ACTOR,
    CREATE,
    ScriptedModel,
    call,
    count,
    final,
)
from tests.integration.test_agent import store as store

pytestmark = pytest.mark.integration


def test_mysql_checkpoint_roundtrip_and_pending_write_order(store):
    run = store.create("checkpoint", ACTOR)
    saver = MySQLSaver(store.factory)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"payload": {"中文": [1, True, None]}}
    config = saver.config(run.id, "", checkpoint["id"])
    saver.put_writes(config, [("payload", {"saved": True})], "task")
    assert saver.get_tuple(config) is None
    saver.put(
        {"configurable": {"thread_id": run.id}}, checkpoint, {"source": "input", "step": 0}, {}
    )
    restored = MySQLSaver(store.factory).get_tuple(config)
    assert restored.checkpoint["channel_values"] == checkpoint["channel_values"]
    assert restored.pending_writes == [("task", "payload", {"saved": True})]
    saver.put_writes(config, [("payload", "must not overwrite")], "task")
    assert saver.get_tuple(config).pending_writes == restored.pending_writes
    saver.put_writes(config, [("__error__", "first")], "task")
    saver.put_writes(config, [("__error__", "second")], "task")
    assert ("task", "__error__", "second") in saver.get_tuple(config).pending_writes
    assert len(list(saver.list({"configurable": {"thread_id": run.id}}, filter={"step": 0}))) == 1
    assert list(saver.list(config, filter={"step": 99})) == []
    assert list(saver.list(config, before=config)) == []


def test_interrupt_survives_new_runtime_and_resume_does_not_approve(store):
    run = asyncio.run(
        AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)])).create("create", ACTOR)
    )
    before = count(store)
    restarted = AgentRuntime(store, ScriptedModel([]))
    state = asyncio.run(restarted.graph.aget_state({"configurable": {"thread_id": run.id}}))
    assert state.next == ("approval",) and state.tasks[0].interrupts
    waiting = asyncio.run(restarted.drive(run.id, ACTOR))
    assert waiting.status == "waiting_confirmation" and count(store) == before
    denied = asyncio.run(restarted.decide(run.id, ACTOR, run.pending_action["action_id"], False))
    assert denied.status == "rejected" and count(store) == before


def test_read_effect_replay_after_node_crash_is_idempotent(store, monkeypatch):
    original = GraphNodes.apply

    async def crash_after_apply(self, state):
        await original(self, state)
        raise RuntimeError("crash before node checkpoint")

    monkeypatch.setattr(GraphNodes, "apply", crash_after_apply)
    runtime = AgentRuntime(
        store, ScriptedModel([call("get_equipment", {"equipment_no": "EQ-10023"})])
    )
    run = store.create("read", ACTOR)
    with pytest.raises(RuntimeError, match="crash"):
        asyncio.run(runtime.drive(run.id, ACTOR))
    assert store.get(run.id, ACTOR).tool_calls == 1
    monkeypatch.setattr(GraphNodes, "apply", original)
    result = asyncio.run(AgentRuntime(store, ScriptedModel([final()])).drive(run.id, ACTOR))
    assert result.status == "completed" and result.tool_calls == 1
    assert len([e for e in result.events if e["kind"] == "tool_result"]) == 1


def test_approval_commit_before_checkpoint_crash_is_not_repeated(store, monkeypatch):
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)]))
    run = asyncio.run(runtime.create("create", ACTOR))
    before = count(store)
    original = store.decide

    def crash_after_commit(*args):
        original(*args)
        raise RuntimeError("crash after committed approval")

    monkeypatch.setattr(store, "decide", crash_after_commit)
    with pytest.raises(RuntimeError, match="committed"):
        asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    assert count(store) == before + 1
    monkeypatch.setattr(store, "decide", original)
    result = asyncio.run(AgentRuntime(store, ScriptedModel([final()])).drive(run.id, ACTOR))
    assert result.status == "completed" and count(store) == before + 1
    assert len([e for e in result.events if e["kind"] == "decision"]) == 1


def test_old_confirmation_does_not_approve_next_action(store):
    runtime = AgentRuntime(
        store,
        ScriptedModel(
            [
                call("create_ticket", CREATE),
                call("create_ticket", {**CREATE, "title": "Second"}, "c2"),
                final(),
            ]
        ),
    )
    first = asyncio.run(runtime.create("two requests", ACTOR))
    second = asyncio.run(runtime.decide(first.id, ACTOR, first.pending_action["action_id"], True))
    assert second.status == "waiting_confirmation"
    before = count(store)
    replay = asyncio.run(runtime.decide(first.id, ACTOR, first.pending_action["action_id"], True))
    assert replay.pending_action["action_id"] == second.pending_action["action_id"]
    assert count(store) == before
    done = asyncio.run(runtime.decide(first.id, ACTOR, second.pending_action["action_id"], False))
    assert done.status == "rejected"


def test_lease_and_fencing(store):
    run = store.create("test", ACTOR)
    store.claim(run.id, ACTOR, "a" * 32)
    with pytest.raises(BusinessError, match="already being processed"):
        store.claim(run.id, ACTOR, "b" * 32)
    with store.factory() as session, session.begin():
        row = session.get(AgentRun, run.id)
        row.graph_lease_until = utc_now() - timedelta(seconds=1)
        row.expires_at = utc_now() - timedelta(seconds=1)
    store.claim(run.id, ACTOR, "b" * 32)
    token = run_owner.set("a" * 32)
    try:
        with pytest.raises(BusinessError, match="ownership changed"):
            store.reserve_step(run.id, ACTOR)
        cp = empty_checkpoint()
        with pytest.raises(BusinessError, match="ownership changed"):
            MySQLSaver(store.factory).put({"configurable": {"thread_id": run.id}}, cp, {}, {})
    finally:
        run_owner.reset(token)
    store.release(run.id, "a" * 32)
    with store.factory() as session:
        assert session.get(AgentRun, run.id).graph_owner == "b" * 32
    store.release(run.id, "b" * 32)
    assert store.get(run.id, ACTOR).status == "running"


def test_graph_expired_approval_never_writes(store):
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)]))
    run = asyncio.run(runtime.create("create", ACTOR))
    with store.factory() as session, session.begin():
        session.get(AgentRun, run.id).expires_at = utc_now() - timedelta(seconds=1)
    before = count(store)
    result = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    assert result.error_code == "approval_expired" and count(store) == before


def test_legacy_pending_run_can_enter_graph(store):
    run = store.create("legacy", ACTOR)
    store.reserve_step(run.id, ACTOR)
    pending = store.apply(run.id, ACTOR, call("create_ticket", CREATE), 1)
    assert MySQLSaver(store.factory).get_tuple({"configurable": {"thread_id": run.id}}) is None
    result = asyncio.run(
        AgentRuntime(store, ScriptedModel([final()])).decide(
            run.id, ACTOR, pending.pending_action["action_id"], True
        )
    )
    assert result.status == "completed"


def test_resume_api_checks_owner_and_does_not_write(store):
    from fastapi.testclient import TestClient

    from opsmind.api.agent import get_runtime
    from opsmind.core.config import Settings
    from opsmind.main import create_app

    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)]))
    run = asyncio.run(runtime.create("create", ACTOR))
    app = create_app(Settings(_env_file=None, database_url=""))
    app.dependency_overrides[get_runtime] = lambda: runtime
    before = count(store)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/agent/runs/{run.id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_confirmation"
    assert count(store) == before
    with pytest.raises(BusinessError, match="another employee"):
        asyncio.run(runtime.drive(run.id, "EMP-1002"))
