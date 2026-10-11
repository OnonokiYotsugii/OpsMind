"""Committed test-database rows exercise actual connections and process restart."""

import asyncio
import json
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from opsmind.agent.checkpoint_models import GraphCheckpoint
from opsmind.agent.models import AgentRun
from opsmind.agent.runtime import AgentRuntime
from opsmind.agent.store import AgentStore
from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.db.models import Employee, Equipment, Ticket
from tests.integration.test_agent import CREATE, ScriptedModel, call, final

pytestmark = pytest.mark.integration


@pytest.fixture
def committed_store(mysql_engine):
    assert mysql_engine.url.database == "opsmind_test"
    factory = sessionmaker(mysql_engine, expire_on_commit=False)
    token = uuid4().hex[:12].upper()
    actor, equipment_no = "EMP-G-" + token, "EQ-G-" + token
    with factory() as session, session.begin():
        employee = Employee(
            employee_no=actor, name="Graph test", department="test", role="admin", status="active"
        )
        equipment = Equipment(
            equipment_no=equipment_no,
            name="Graph test",
            model="test",
            manufacturer="test",
            status="active",
            location="test",
        )
        session.add_all([employee, equipment])
        session.flush()
        employee_id, equipment_id = employee.id, equipment.id
    store = AgentStore(factory, Settings(_env_file=None))
    try:
        yield store, actor, equipment_no
    finally:
        # Only this fixture's uniquely identified rows in the dedicated test database.
        with factory() as session, session.begin():
            runs = list(session.scalars(select(AgentRun.id).where(AgentRun.actor_no == actor)))
            if runs:
                session.execute(delete(GraphCheckpoint).where(GraphCheckpoint.run_id.in_(runs)))
                session.execute(delete(AgentRun).where(AgentRun.id.in_(runs)))
            session.execute(delete(Ticket).where(Ticket.equipment_id == equipment_id))
            session.execute(delete(Equipment).where(Equipment.id == equipment_id))
            session.execute(delete(Employee).where(Employee.id == employee_id))


def ticket_count(store, equipment_no):
    with store.factory() as session:
        return session.scalar(
            select(func.count())
            .select_from(Ticket)
            .join(Equipment)
            .where(Equipment.equipment_no == equipment_no)
        )


def test_new_python_process_resumes_mysql_checkpoint(committed_store):
    store, actor, equipment = committed_store
    runtime = AgentRuntime(
        store, ScriptedModel([call("create_ticket", {**CREATE, "equipment_no": equipment})])
    )
    run = asyncio.run(runtime.create("create", actor))
    code = r"""
import asyncio, json, sys
from sqlalchemy.orm import sessionmaker
from opsmind.core.config import Settings
from opsmind.db.session import create_db_engine, validated_mysql_url
from opsmind.agent.store import AgentStore
from opsmind.agent.runtime import AgentRuntime
from opsmind.llm.tool_protocol import ToolTurn
class Model:
    async def complete_tools(self, messages, tools):
        return ToolTurn({"role":"assistant","content":"Done"}, None)
s=Settings()
raw=s.test_database_url.get_secret_value()
url=validated_mysql_url(raw)
assert url.database == "opsmind_test" and url.host in {"127.0.0.1","localhost"}
e=create_db_engine(raw)
r=AgentRuntime(AgentStore(sessionmaker(e,expire_on_commit=False),s),Model())
result=asyncio.run(r.decide(sys.argv[1],sys.argv[2],sys.argv[3],True))
receipts = [x for x in result.events if x["kind"] == "decision"]
print(json.dumps({"status":result.status,"receipts":len(receipts)}))
e.dispose()
"""
    output = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, run.id, actor, run.pending_action["action_id"]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout) == {"status": "completed", "receipts": 1}
    assert ticket_count(store, equipment) == 1


def test_concurrent_graph_confirmation_only_one_writer(committed_store):
    store, actor, equipment = committed_store
    runtime = AgentRuntime(
        store, ScriptedModel([call("create_ticket", {**CREATE, "equipment_no": equipment})])
    )
    run = asyncio.run(runtime.create("create", actor))

    async def confirm_both():
        first = AgentRuntime(AgentStore(store.factory, store.settings), ScriptedModel([final()]))
        second = AgentRuntime(AgentStore(store.factory, store.settings), ScriptedModel([final()]))
        return await asyncio.gather(
            first.decide(run.id, actor, run.pending_action["action_id"], True),
            second.decide(run.id, actor, run.pending_action["action_id"], True),
            return_exceptions=True,
        )

    results = asyncio.run(confirm_both())
    assert any(not isinstance(r, Exception) and r.status == "completed" for r in results)
    assert all(
        not isinstance(r, Exception) or (isinstance(r, BusinessError) and r.code == "run_busy")
        for r in results
    )
    assert ticket_count(store, equipment) == 1
    saved = store.get(run.id, actor)
    assert len([e for e in saved.events if e["kind"] == "decision"]) == 1
