"""Short MySQL transactions; no LLM network calls while a transaction is open."""

import time
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsmind.agent.execution import check_owner
from opsmind.agent.models import AgentRun
from opsmind.agent.prompts import SYSTEM_PROMPT
from opsmind.agent.state import event, expire, fail, observation, snapshot, write_receipt_summary
from opsmind.core.config import Settings
from opsmind.core.errors import BusinessError
from opsmind.db.models import utc_now
from opsmind.llm.tool_protocol import ToolTurn
from opsmind.rag.citations import checked_answer
from opsmind.schemas.agent import RunRead
from opsmind.services.tickets import get_actor
from opsmind.tools.executor import execute_read
from opsmind.tools.registry import TOOLS, Risk, validate_call


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
        check_owner(row)
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
            event(row, "started", trace_version=1)
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

    def apply(
        self,
        run_id: str,
        actor: str,
        turn: ToolTurn,
        elapsed_ms: int,
        knowledge_result: dict | None = None,
        effect_id: str | None = None,
        knowledge_ms: int = 0,
    ) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            if row.status != "running":
                return snapshot(row)
            if effect_id:
                if any(e.get("effect_id") == effect_id for e in row.events):
                    return snapshot(row)
                event(row, "graph_effect", effect_id=effect_id)
            row.elapsed_ms += elapsed_ms
            if row.elapsed_ms >= row.time_budget_ms:
                fail(row, "agent_timeout")
                return snapshot(row)
            if turn.call is None:
                row.messages = [*row.messages, turn.message]
                row.result = write_receipt_summary(row.events) or checked_answer(
                    turn.message["content"], row.messages
                )
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
            tool_outcome = "error"
            try:
                definition, params = validate_call(call.function.name, call.function.arguments)
                if definition.risk == Risk.LOW:
                    if definition.name == "search_knowledge":
                        result = knowledge_result or {"ok": False, "error": "knowledge_unavailable"}
                    else:
                        result = execute_read(session, definition, params)
                    tool_outcome = "success" if result["ok"] else "error"
                    if definition.name == "search_knowledge" and result["ok"]:
                        event(
                            row,
                            "retrieval",
                            call_id=call.id,
                            items=[
                                {
                                    k: item[k]
                                    for k in (
                                        "citation",
                                        "source",
                                        "version",
                                        "heading",
                                        "distance",
                                    )
                                }
                                for item in result["data"].get("items", [])[:5]
                            ],
                        )
                    observation(row, call.id, result)
                    event(row, "tool_result", tool=definition.name, ok=result["ok"])
                else:
                    employee = get_actor(session, actor)
                    if employee.role == "requester" and (
                        definition.name == "update_ticket" or getattr(params, "assigned_to", None)
                    ):
                        raise BusinessError(
                            "tool_forbidden", "Employee cannot perform this action.", 403
                        )
                    tool_outcome = "proposed"
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
                duration = max(1, round((time.monotonic() - tool_started) * 1000))
                event(
                    row,
                    "tool_span",
                    tool=call.function.name if call.function.name in TOOLS else "unknown",
                    call_id=call.id,
                    duration_ms=duration + knowledge_ms,
                    outcome=tool_outcome,
                )
                row.elapsed_ms += duration
                if row.elapsed_ms >= row.time_budget_ms:
                    fail(row, "agent_timeout")
            return snapshot(row)

    def may_search(self, run_id: str, actor: str, call_id: str) -> bool:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            prior_ids = {c["id"] for msg in row.messages for c in msg.get("tool_calls", [])}
            return (
                row.status == "running"
                and row.tool_calls < row.max_tool_calls
                and call_id not in prior_ids
                and row.elapsed_ms < row.time_budget_ms
            )

    def correct_multiple_calls(self, run_id: str, actor: str, elapsed_ms: int) -> None:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            expire(row)
            if row.status != "running":
                return
            row.elapsed_ms += elapsed_ms
            row.messages = [
                *row.messages,
                {
                    "role": "system",
                    "content": "刚才返回了多个工具调用，程序全部拒绝，没有执行任何一个。"
                    "下一轮只选择一个最先需要的工具，等待结果后再选择下一个。",
                },
            ]
            event(row, "protocol_correction", code="llm_multiple_tool_calls")

    def mark_failed(self, run_id: str, actor: str, code: str) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            if row.status == "running":
                fail(row, code)
            return snapshot(row)

    def decide(self, run_id: str, actor: str, action_id: str, approved: bool):
        from opsmind.agent.approval import decide

        return decide(self, run_id, actor, action_id, approved)

    def claim(self, run_id: str, actor: str, owner: str) -> None:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            if row.graph_owner and row.graph_lease_until and row.graph_lease_until > utc_now():
                raise BusinessError(
                    "run_busy", "This run is already being processed; retry later.", 409
                )
            if not any(e["kind"] == "graph_enabled" for e in row.events):
                event(row, "graph_enabled", version=1)
            row.graph_owner = owner
            row.graph_lease_until = utc_now() + timedelta(seconds=420)

    def release(self, run_id: str, owner: str) -> None:
        with self.factory() as session, session.begin():
            row = session.get(AgentRun, run_id, with_for_update=True)
            if row and row.graph_owner == owner:
                row.graph_owner = None
                row.graph_lease_until = None

    def validate_decision(self, run_id: str, actor: str, action_id: str, approved: bool) -> RunRead:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            for receipt in row.events:
                if receipt["kind"] == "decision" and receipt["action_id"] == action_id:
                    if receipt["approved"] != approved:
                        raise BusinessError(
                            "decision_conflict", "Action already has a different decision."
                        )
                    return snapshot(row)
            expire(row)
            if row.status == "failed":
                return snapshot(row)
            if row.status != "waiting_confirmation" or row.pending_action is None:
                raise BusinessError("no_pending_action", "Run is not awaiting confirmation.")
            if row.pending_action["action_id"] != action_id:
                raise BusinessError(
                    "action_mismatch", "Confirmation does not match the pending action."
                )
            return snapshot(row)

    def remaining_budget(self, run_id: str, actor: str) -> int:
        with self.factory() as session:
            row = self.load(session, run_id, actor)
            return max(0, row.time_budget_ms - row.elapsed_ms)

    def record_model(
        self, run_id: str, actor: str, kind: str, trace_id: str, details: dict
    ) -> None:
        with self.factory() as session, session.begin():
            row = self.load(session, run_id, actor)
            if any(e["kind"] == kind and e.get("trace_id") == trace_id for e in row.events):
                return
            event(row, kind, trace_id=trace_id, **details)
