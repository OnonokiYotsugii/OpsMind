"""Approval receipt and business writes commit atomically under a run row lock."""

import json
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from opsmind.agent.state import event, expire, observation, snapshot
from opsmind.core.errors import BusinessError
from opsmind.db.models import utc_now
from opsmind.observability.trace import approval_wait
from opsmind.tools.executor import execute_approved_write
from opsmind.tools.registry import validate_call

if TYPE_CHECKING:
    from opsmind.agent.store import AgentStore


def decide(store: "AgentStore", run_id: str, actor: str, action_id: str, approved: bool):
    with store.factory() as session, session.begin():
        row = store.load(session, run_id, actor)
        expire(row)
        for receipt in row.events:
            if receipt["kind"] == "decision" and receipt["action_id"] == action_id:
                if receipt["approved"] != approved:
                    raise BusinessError(
                        "decision_conflict", "Action already has a different decision."
                    )
                # Same decision returns persisted state; never writes or resumes twice.
                return snapshot(row), False
        expire(row)
        if row.status == "failed" and row.error_code == "approval_expired":
            return snapshot(row), False
        action = row.pending_action
        if row.status != "waiting_confirmation" or action is None:
            raise BusinessError("no_pending_action", "Run is not awaiting confirmation.")
        if action["action_id"] != action_id:
            raise BusinessError(
                "action_mismatch", "Confirmation does not match the pending action."
            )
        wait_ms = approval_wait(row.events, action_id)
        if not approved:
            observation(row, action["tool_call_id"], {"ok": False, "error": "user_rejected"})
            row.status = "rejected"
            row.result = "本次待确认操作已拒绝，未执行该操作。"
            event(
                row,
                "decision",
                action_id=action_id,
                tool=action["tool"],
                approved=False,
                ok=False,
                wait_ms=wait_ms,
            )
            row.pending_action = None
            return snapshot(row), False

        write_started = time.monotonic()
        try:
            # A savepoint rolls back business changes on failure but retains the failed receipt.
            with session.begin_nested():
                definition, params = validate_call(action["tool"], json.dumps(action["arguments"]))
                result = execute_approved_write(session, definition, params, actor)
        except BusinessError as exc:
            result = {"ok": False, "error": exc.code, "message": exc.message}
        except SQLAlchemyError:
            result = {"ok": False, "error": "write_failed", "message": "Business write failed."}
        event(
            row,
            "decision",
            action_id=action_id,
            tool=action["tool"],
            arguments=action["arguments"],
            approved=True,
            ok=result["ok"],
            result=result,
            wait_ms=wait_ms,
            duration_ms=max(1, round((time.monotonic() - write_started) * 1000)),
        )
        observation(row, action["tool_call_id"], result)
        row.elapsed_ms += max(1, round((time.monotonic() - write_started) * 1000))
        row.pending_action = None
        row.status = "running"
        row.expires_at = utc_now() + timedelta(
            milliseconds=max(1, row.time_budget_ms - row.elapsed_ms) + 15000,
        )
        return snapshot(row), True
