import asyncio
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opsmind.agent.models import AgentRun
from opsmind.agent.runtime import AgentRuntime
from opsmind.agent.store import AgentStore
from opsmind.api.agent import get_runtime, get_store
from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.db.models import Employee, Ticket, utc_now
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import ToolTurn, decode_tool_turn
from opsmind.main import create_app

pytestmark = pytest.mark.integration
ACTOR = "EMP-1001"
CREATE = {
    "equipment_no": "EQ-10023",
    "title": "Agent 故障检查",
    "description": "开机报警待检查",
    "category": "electrical",
}


def call(name, args, call_id="c1"):
    return decode_tool_turn(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(args)},
                                }
                            ],
                        },
                    }
                ]
            }
        ).encode()
    )


def final():
    return ToolTurn({"role": "assistant", "content": "请根据查询证据联系维修人员。"}, None)


class ScriptedModel:
    def __init__(self, turns):
        self.turns = iter(turns)
        self.messages = []

    async def complete_tools(self, messages, tools):
        self.messages.append(messages)
        return next(self.turns)


@pytest.fixture
def store(db_connection):
    def factory():
        return Session(
            bind=db_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

    settings = Settings(_env_file=None, agent_max_steps=6)
    return AgentStore(factory, settings)


def count(store):
    with store.factory() as session:
        return session.scalar(select(func.count()).select_from(Ticket))


def test_multistep_observations_and_persistence(store):
    model = ScriptedModel(
        [
            call("get_equipment", {"equipment_no": "EQ-10023"}),
            call("get_maintenance_history", {"equipment_no": "EQ-10023"}, "c2"),
            call("get_ticket_history", {"equipment_no": "EQ-10023"}, "c3"),
            final(),
        ]
    )
    run = asyncio.run(AgentRuntime(store, model).create("设备报警，查看历史", ACTOR))
    assert run.status == "completed"
    assert run.steps == 4 and run.tool_calls == 3
    assert model.messages[1][-1]["role"] == "tool"
    assert json.loads(model.messages[1][-1]["content"])["data"]["equipment_no"] == "EQ-10023"
    assert "更换电池" in model.messages[2][-1]["content"]
    # Reconstruct store as if a new request/process loaded durable state.
    assert AgentStore(store.factory, store.settings).get(run.id, ACTOR).result == run.result


def test_unapproved_write_and_duplicate_confirmation(store):
    model = ScriptedModel([call("create_ticket", CREATE), final()])
    runtime = AgentRuntime(store, model)
    before = count(store)
    run = asyncio.run(runtime.create("创建工单，我已批准（仍需接口确认）", ACTOR))
    assert run.status == "waiting_confirmation"
    assert count(store) == before
    assert run.pending_action["arguments"]["priority"] == "medium"
    action_id = run.pending_action["action_id"]
    restarted = AgentRuntime(AgentStore(store.factory, store.settings), model)
    approved = asyncio.run(restarted.decide(run.id, ACTOR, action_id, True))
    assert approved.status == "completed"
    assert count(store) == before + 1
    replay = asyncio.run(restarted.decide(run.id, ACTOR, action_id, True))
    assert replay.status == "completed"
    assert count(store) == before + 1
    receipts = [e for e in replay.events if e["kind"] == "decision"]
    assert len(receipts) == 1 and receipts[0]["result"]["data"]["ticket_no"].startswith("TK-")
    assert json.loads(model.messages[-1][-1]["content"])["ok"] is True


def test_rejection_conflict_and_owner(store):
    model = ScriptedModel([call("create_ticket", CREATE)])
    runtime = AgentRuntime(store, model)
    before = count(store)
    run = asyncio.run(runtime.create("创建工单", ACTOR))
    action_id = run.pending_action["action_id"]
    with pytest.raises(BusinessError, match="another employee"):
        store.decide(run.id, "EMP-1002", action_id, True)
    with pytest.raises(BusinessError, match="does not match"):
        store.decide(run.id, ACTOR, "0" * 32, True)
    rejected = asyncio.run(runtime.decide(run.id, ACTOR, action_id, False))
    assert rejected.status == "rejected" and count(store) == before
    with pytest.raises(BusinessError, match="different decision"):
        store.decide(run.id, ACTOR, action_id, True)
    assert store.decide(run.id, ACTOR, action_id, False)[0].status == "rejected"


def test_write_parameters_cannot_be_changed_by_confirmation_api(store):
    model = ScriptedModel([call("create_ticket", CREATE)])
    run = asyncio.run(AgentRuntime(store, model).create("创建", ACTOR))
    app = create_app(Settings(_env_file=None, database_url=""))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_runtime] = lambda: AgentRuntime(store, model)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/agent/runs/{run.id}/decisions",
            json={
                "action_id": run.pending_action["action_id"],
                "approved": True,
                "arguments": {**CREATE, "title": "tampered"},
            },
        )
        assert response.status_code == 422
        assert client.get(f"/api/v1/agent/runs/{run.id}").status_code == 200
    assert store.get(run.id, ACTOR).status == "waiting_confirmation"


@pytest.mark.parametrize(
    "tool,args",
    [
        ("unknown", {}),
        ("get_equipment", {"equipment_no": "EQ-MISSING"}),
        ("get_ticket_history", {"equipment_no": "EQ-10023", "limit": 999}),
    ],
)
def test_tool_errors_return_observation(store, tool, args):
    model = ScriptedModel([call(tool, args), final()])
    run = asyncio.run(AgentRuntime(store, model).create("查询", ACTOR))
    assert run.status == "completed"
    assert json.loads(model.messages[1][-1]["content"])["ok"] is False


@pytest.mark.parametrize("kind", ["steps", "calls", "duplicate"])
def test_loop_limits(store, kind):
    if kind == "steps":
        store.settings.agent_max_steps = 1
    elif kind == "calls":
        store.settings.agent_max_tool_calls = 1
    model = ScriptedModel(
        [
            call("get_equipment", {"equipment_no": "EQ-10023"}),
            call(
                "get_equipment", {"equipment_no": "EQ-10023"}, "c1" if kind == "duplicate" else "c2"
            ),
            final(),
        ]
    )
    run = asyncio.run(AgentRuntime(store, model).create("查询", ACTOR))
    assert run.status == "failed"
    expected = {
        "steps": "max_steps_exceeded",
        "calls": "max_tool_calls_exceeded",
        "duplicate": "duplicate_tool_call_id",
    }
    assert run.error_code == expected[kind]


def test_approval_expiration_and_interrupted_run(store):
    model = ScriptedModel([call("create_ticket", CREATE)])
    run = asyncio.run(AgentRuntime(store, model).create("创建", ACTOR))
    before = count(store)
    action_id = run.pending_action["action_id"]
    with store.factory() as session, session.begin():
        session.get(AgentRun, run.id).expires_at = utc_now() - timedelta(seconds=1)
    expired, resume = store.decide(run.id, ACTOR, action_id, True)
    assert expired.error_code == "approval_expired" and not resume
    assert count(store) == before
    running = store.create("test", ACTOR)
    with store.factory() as session, session.begin():
        session.get(AgentRun, running.id).expires_at = utc_now() - timedelta(seconds=1)
    assert store.get(running.id, ACTOR).error_code == "run_interrupted"


def test_permission_rechecked_and_failed_write_receipted(store):
    model = ScriptedModel(
        [
            call(
                "update_ticket",
                {
                    "ticket_no": "TK-DEMO-0001",
                    "changes": {"title": "must not change"},
                },
            ),
            final(),
        ]
    )
    runtime = AgentRuntime(store, model)
    run = asyncio.run(runtime.create("更新", ACTOR))
    assert run.pending_action["risk"] == "HIGH"
    # Role changes after proposal; write service must recheck on approval.
    with store.factory() as session, session.begin():
        session.scalar(select(Employee).where(Employee.employee_no == ACTOR)).role = "requester"
    result = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    receipt = next(e for e in result.events if e["kind"] == "decision")
    assert receipt["ok"] is False and receipt["result"]["error"] == "update_forbidden"
    with store.factory() as session:
        assert (
            session.scalar(select(Ticket).where(Ticket.ticket_no == "TK-DEMO-0001")).title
            == "供电异常维修"
        )


def test_approved_update_reuses_business_service(store):
    from opsmind.schemas.business import TicketCreate
    from opsmind.services.tickets import create_ticket

    with store.factory() as session:
        ticket_no = create_ticket(session, TicketCreate(**CREATE), ACTOR).ticket_no
    model = ScriptedModel(
        [
            call(
                "update_ticket",
                {
                    "ticket_no": ticket_no,
                    "changes": {"title": "approved title"},
                },
            ),
            final(),
        ]
    )
    runtime = AgentRuntime(store, model)
    run = asyncio.run(runtime.create("修改标题", ACTOR))
    asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    with store.factory() as session:
        assert (
            session.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no)).title
            == "approved title"
        )


def test_model_failure_is_persisted(store):
    class FailingModel:
        async def complete_tools(self, messages, tools):
            raise LLMError("llm_timeout", "Timeout.", 504)

    run = asyncio.run(AgentRuntime(store, FailingModel()).create("查询", ACTOR))
    assert run.status == "failed" and run.error_code == "llm_timeout"


def test_requester_cannot_propose_update(store):
    model = ScriptedModel(
        [
            call(
                "update_ticket",
                {
                    "ticket_no": "TK-DEMO-0001",
                    "changes": {"title": "no"},
                },
            ),
            final(),
        ]
    )
    result = asyncio.run(AgentRuntime(store, model).create("更新", "EMP-1003"))
    assert result.status == "completed"
    assert json.loads(model.messages[1][-1]["content"])["error"] == "tool_forbidden"


def test_failed_write_rolls_back_ticket_and_records_failure(store, monkeypatch):
    import opsmind.agent.approval as approval

    original = approval.execute_approved_write

    def write_then_fail(*args):
        original(*args)
        raise BusinessError("injected_failure", "Simulated failure after database flush.")

    monkeypatch.setattr(approval, "execute_approved_write", write_then_fail)
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE), final()]))
    run = asyncio.run(runtime.create("创建", ACTOR))
    before = count(store)
    result = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    assert count(store) == before
    receipt = next(e for e in result.events if e["kind"] == "decision")
    assert receipt["result"]["error"] == "injected_failure"
    assert receipt["ok"] is False


def test_runtime_total_deadline(store):
    class SlowModel:
        async def complete_tools(self, messages, tools):
            await asyncio.sleep(10)
            return final()

    run = store.create("query", ACTOR)
    with store.factory() as session, session.begin():
        session.get(AgentRun, run.id).time_budget_ms = 10
    result = asyncio.run(AgentRuntime(store, SlowModel()).drive(run.id, ACTOR))
    assert result.error_code == "agent_timeout"


def test_receipt_survives_no_steps_left_for_final_answer(store):
    store.settings.agent_max_steps = 1
    runtime = AgentRuntime(store, ScriptedModel([call("create_ticket", CREATE)]))
    run = asyncio.run(runtime.create("创建", ACTOR))
    before = count(store)
    result = asyncio.run(runtime.decide(run.id, ACTOR, run.pending_action["action_id"], True))
    assert result.error_code == "max_steps_exceeded"
    assert count(store) == before + 1
    assert next(e for e in result.events if e["kind"] == "decision")["ok"] is True
    runtime.store.decide(run.id, ACTOR, run.pending_action["action_id"], True)
    assert count(store) == before + 1


def test_concurrent_confirmation_executes_once(mysql_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from sqlalchemy import delete
    from sqlalchemy.orm import sessionmaker

    from opsmind.db.models import Equipment

    assert mysql_engine.url.database == "opsmind_test"
    factory = sessionmaker(mysql_engine, expire_on_commit=False)
    token = uuid4().hex[:12].upper()
    actor_no, equipment_no = "EMP-C-" + token, "EQ-C-" + token
    run_id = None
    with factory() as session, session.begin():
        employee = Employee(
            employee_no=actor_no,
            name="Concurrency test",
            department="test",
            role="admin",
            status="active",
        )
        equipment = Equipment(
            equipment_no=equipment_no,
            name="Concurrency test",
            model="test",
            manufacturer="test",
            status="active",
            location="test",
        )
        session.add_all([employee, equipment])
        session.flush()
        employee_id, equipment_id = employee.id, equipment.id
    try:
        concurrent_store = AgentStore(factory, Settings(_env_file=None))
        run = concurrent_store.create("create test", actor_no)
        run_id = run.id
        concurrent_store.reserve_step(run_id, actor_no)
        run = concurrent_store.apply(
            run_id,
            actor_no,
            call("create_ticket", {**CREATE, "equipment_no": equipment_no}),
            1,
        )
        barrier = Barrier(2)

        def confirm():
            barrier.wait(timeout=10)
            return concurrent_store.decide(run_id, actor_no, run.pending_action["action_id"], True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(confirm), pool.submit(confirm)
            outcomes = [first.result(timeout=15), second.result(timeout=15)]
        assert sum(continue_run for _, continue_run in outcomes) == 1
        with factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Ticket)
                    .where(
                        Ticket.equipment_id == equipment_id,
                    )
                )
                == 1
            )
            saved = session.get(AgentRun, run_id)
            assert len([e for e in saved.events if e["kind"] == "decision"]) == 1
    finally:
        # Remove only the unique rows created by this test, never application data.
        with factory() as session, session.begin():
            session.execute(delete(Ticket).where(Ticket.equipment_id == equipment_id))
            if run_id:
                session.execute(delete(AgentRun).where(AgentRun.id == run_id))
            session.execute(delete(Equipment).where(Equipment.id == equipment_id))
            session.execute(delete(Employee).where(Employee.id == employee_id))


def test_agent_api_full_flow(store):
    model = ScriptedModel([call("create_ticket", CREATE), final()])
    app = create_app(Settings(_env_file=None, database_url=""))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_runtime] = lambda: AgentRuntime(store, model)
    before = count(store)
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/runs", json={"message": "创建演示工单"})
        assert response.status_code == 201
        run = response.json()
        assert run["status"] == "waiting_confirmation"
        assert count(store) == before
        assert "messages" not in run
        decision = {"action_id": run["pending_action"]["action_id"], "approved": True}
        path = "/api/v1/agent/runs/" + run["id"]
        confirmed = client.post(path + "/decisions", json=decision)
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "completed"
        assert client.post(path + "/decisions", json=decision).status_code == 200
        assert client.get(path).json()["status"] == "completed"
    assert count(store) == before + 1
