"""Small helpers for durable run state."""

import json

from opsmind.agent.models import AgentRun
from opsmind.db.models import utc_now
from opsmind.schemas.agent import RunRead


def snapshot(row: AgentRun) -> RunRead:
    return RunRead.model_validate(row)


def event(row: AgentRun, kind: str, **fields) -> None:
    row.events = [*row.events, {"kind": kind, "at": utc_now().isoformat() + "Z", **fields}]


def fail(row: AgentRun, code: str) -> None:
    row.status = "failed"
    row.error_code = code
    row.pending_action = None
    event(row, "failed", code=code)


def expire(row: AgentRun) -> None:
    if row.status in {"running", "waiting_confirmation"} and row.expires_at < utc_now():
        fail(row, "approval_expired" if row.status == "waiting_confirmation" else "run_interrupted")


def observation(row: AgentRun, call_id: str, result: dict) -> None:
    content = json.dumps(result, ensure_ascii=False)
    if len(content) > 8000:
        content = json.dumps(
            {
                "ok": False,
                "error": "tool_result_too_large",
                "message": "Reduce the history limit or request narrower information.",
            }
        )
    row.messages = [*row.messages, {"role": "tool", "tool_call_id": call_id, "content": content}]
