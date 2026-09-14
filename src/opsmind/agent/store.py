"""Short MySQL transactions; no LLM network calls while a transaction is open."""

import time
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.agent.models import AgentRun
from opsmind.agent.prompts import SYSTEM_PROMPT
from opsmind.agent.state import event, expire, fail, observation, snapshot
from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.db.models import utc_now
from opsmind.llm.tool_protocol import ToolTurn
from opsmind.schemas.agent import RunRead
from opsmind.services.tickets import get_actor
from opsmind.tools.executor import execute_read
from opsmind.tools.registry import Risk, validate_call


class AgentStore:
    def __init__(self, factory: Callable[[], Session], settings: Settings):
        self.factory = factory
        self.settings = settings

    def load(self, session: Session, run_id: str, actor: str) -> AgentRun:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if row is None:
            raise BusinessError("run_not_found", "Agent run does not exist.", 404)
        if row.actor_no != actor:
            raise BusinessError("run_forbidden", "This run belongs to another employee.", 403)
        get_actor(session, actor)
        return row

    def create(self, message: str, actor: str) -> RunRead:
        with self.factory() as session, session.begin():
            get_actor(session, actor)
            row = AgentRun(
                id=uuid4().hex,
                actor_no=actor,
                status="running",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                events=[],
                pending_action=None,
                result=None,
                error_code=None,
                steps=0,
                tool_calls=0,
                elapsed_ms=0,
                max_steps=self.settings.agent_max_steps,
                max_tool_calls=self.settings.agent_max_tool_calls,
                time_budget_ms=self.settings.agent_timeout_seconds * 1000,
                expires_at=utc_now() + timedelta(seconds=self.settings.agent_timeout_seconds + 15),
            )
            session.add(row)
            session.flush()
            event(row, "started")
            return snapshot(row)

    def get(self, run_id: str, actor: str) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            return snapshot(row)

    def reserve_step(self, run_id: str, actor: str) -> tuple[list, int] | None:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            if row.status != "running":
                return None
            if row.steps >= row.max_steps:
                fail(row, "max_steps_exceeded")
                return None
            if row.elapsed_ms >= row.time_budget_ms:
                fail(row, "agent_timeout")
                return None
            row.steps += 1
            event(row, "model_step", step=row.steps)
            return row.messages, row.time_budget_ms - row.elapsed_ms

    def apply(self, run_id: str, actor: str, turn: ToolTurn, elapsed_ms: int) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            if row.status != "running":
                return snapshot(row)
            row.elapsed_ms += elapsed_ms
            if row.elapsed_ms >= row.time_budget_ms:
                fail(row, "agent_timeout")
                return snapshot(row)
            if turn.call is None:
                row.messages = [*row.messages, turn.message]
                row.result = turn.message["content"]
                row.status = "completed"
                event(row, "completed")
                return snapshot(row)
            call = turn.call
            prior_ids = {c["id"] for msg in row.messages for c in msg.get("tool_calls", [])}
            if call.id in prior_ids:
                fail(row, "duplicate_tool_call_id")
                return snapshot(row)
            if row.tool_calls >= row.max_tool_calls:
                fail(row, "max_tool_calls_exceeded")
                return snapshot(row)
            row.tool_calls += 1
            row.messages = [*row.messages, turn.message]
            tool_started = time.monotonic()
            try:
                definition, params = validate_call(call.function.name, call.function.arguments)
                if definition.risk == Risk.LOW:
                    result = execute_read(session, definition, params)
                    observation(row, call.id, result)
                    event(row, "tool_result", tool=definition.name, ok=True)
                else:
                    employee = get_actor(session, actor)
                    if employee.role == "requester" and (
                        definition.name == "update_ticket" or getattr(params, "assigned_to", None)
                    ):
                        raise BusinessError(
                            "tool_forbidden", "Employee cannot perform this action.", 403
                        )
                    row.pending_action = {
                        "action_id": uuid4().hex,
                        "tool_call_id": call.id,
                        "tool": definition.name,
                        "risk": definition.risk.value,
                        "arguments": params.model_dump(
                            mode="json",
                            exclude_unset=definition.name == "update_ticket",
                        ),
                    }
                    row.status = "waiting_confirmation"
                    row.expires_at = utc_now() + timedelta(
                        seconds=self.settings.agent_approval_ttl_seconds,
                    )
                    row.pending_action = {
                        **row.pending_action,
                        "expires_at": row.expires_at.isoformat() + "Z",
                    }
                    event(
                        row,
                        "confirmation_required",
                        tool=definition.name,
                        action_id=row.pending_action["action_id"],
                    )
            except BusinessError as exc:
                observation(row, call.id, {"ok": False, "error": exc.code, "message": exc.message})
                event(row, "tool_result", tool=call.function.name, ok=False, code=exc.code)
            finally:
                row.elapsed_ms += max(1, round((time.monotonic() - tool_started) * 1000))
                if row.elapsed_ms >= row.time_budget_ms:
                    fail(row, "agent_timeout")
            return snapshot(row)

    def mark_failed(self, run_id: str, actor: str, code: str) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            if row.status == "running":
                fail(row, code)
            return snapshot(row)

    def decide(self, run_id: str, actor: str, action_id: str, approved: bool):
        from opsmind.agent.approval import decide

        return decide(self, run_id, actor, action_id, approved)
