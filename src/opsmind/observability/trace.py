"""Safe event projection and explicitly scoped per-run metrics."""

from datetime import UTC, datetime

FIELDS = {
    "trace_version",
    "kind",
    "at",
    "trace_id",
    "tool",
    "call_id",
    "action_id",
    "step",
    "ok",
    "code",
    "duration_ms",
    "usage",
    "attempts",
    "model",
    "outcome",
    "items",
    "wait_ms",
}


def project_events(events: list[dict]) -> list[dict]:
    return [{key: value for key, value in e.items() if key in FIELDS} for e in events]


def metrics(events: list[dict]) -> dict:
    modern = any(e.get("trace_version") == 1 for e in events)
    starts = {e["trace_id"] for e in events if e["kind"] == "model_start"}
    ends = {e["trace_id"]: e for e in events if e["kind"] == "model_end"}
    known = [e["usage"] for e in ends.values() if e.get("usage") is not None]
    complete = (
        modern
        and bool(starts)
        and sum(e["kind"] == "model_step" for e in events) == len(starts)
        and starts == ends.keys()
        and all(e.get("usage") is not None and e.get("attempts") == 1 for e in ends.values())
    )
    tokens = {
        key: sum(u[key] for u in known)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    tools = [e for e in events if e["kind"] == "tool_span"]
    writes = [e for e in events if e["kind"] == "decision" and e.get("approved")]
    durations = [
        e["duration_ms"]
        for e in [*ends.values(), *tools, *writes]
        if e.get("duration_ms") is not None
    ]
    return {
        "coverage": "v1" if modern else "legacy_partial",
        "model_calls": len(starts) if modern else None,
        "model_calls_without_end": len(starts - ends.keys()),
        "token_usage": tokens if complete else None,
        "observed_token_usage": tokens if known else None,
        "token_usage_complete": complete,
        "tool_calls": len(tools) if modern else None,
        "tool_errors": sum(e["outcome"] == "error" for e in tools),
        "write_executions": len(writes),
        "write_errors": sum(not e["ok"] for e in writes),
        "model_errors": sum(not e["ok"] for e in ends.values()),
        "observed_processing_ms": sum(durations) if modern else None,
        "approval_wait_ms": sum(e.get("wait_ms", 0) for e in events if e["kind"] == "decision"),
    }


def approval_wait(events: list[dict], action_id: str) -> int:
    proposed = next(
        (e for e in events if e["kind"] == "confirmation_required" and e["action_id"] == action_id),
        None,
    )
    if proposed is None:
        return 0
    then = datetime.fromisoformat(proposed["at"].replace("Z", "+00:00"))
    return max(0, round((datetime.now(UTC) - then).total_seconds() * 1000))


def build_trace(run) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "error_code": run.error_code,
        "metrics": metrics(run.events),
        "events": project_events(run.events),
        "note": "Processing excludes human wait and checkpoint IO. Missing usage is unknown.",
    }
