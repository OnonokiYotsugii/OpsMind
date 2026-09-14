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


def write_receipt_summary(events: list[dict]) -> str | None:
    """Business write status must come from committed receipts, not generated prose."""
    decisions = [item for item in events if item["kind"] == "decision" and item.get("approved")]
    if not decisions:
        return None
    lines = ["已确认操作的执行结果（以数据库执行凭据为准）："]
    for item in decisions:
        result = item["result"]
        if item["ok"]:
            number = result["data"]["ticket_no"]
            lines.append(f"- {item['tool']} 已成功执行，工单编号：{number}。")
        else:
            lines.append(f"- {item['tool']} 执行失败：{result['error']}，本次操作未保存。")
    return "\n".join(lines)
