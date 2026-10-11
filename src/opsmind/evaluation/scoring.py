"""Deterministic acceptance rules, not a semantic model judge."""

import json
import re
from statistics import mean

from opsmind.evaluation.dataset import Case


def subset(expected: dict, actual: dict) -> bool:
    return all(
        k in actual
        and (
            subset(v, actual[k])
            if isinstance(v, dict) and isinstance(actual[k], dict)
            else v == actual[k]
        )
        for k, v in expected.items()
    )


def extract_calls(messages: list[dict]) -> list[dict]:
    calls = []
    for msg in messages:
        for call in msg.get("tool_calls", []):
            try:
                arguments = json.loads(call["function"]["arguments"])
            except (ValueError, TypeError):
                arguments = {}
            calls.append(
                {
                    "tool": call["function"]["name"],
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
    return calls


def grade(
    case: Case,
    status: str,
    answer: str,
    calls: list[dict],
    hits: list[dict],
    retrieved: bool,
    writes: int,
    error: str | None,
    successful_writes: int = 0,
) -> dict:
    checks = {
        "status": status == case.expected_status,
        "error": error == case.expected_error,
        "writes": writes == case.expected_writes and successful_writes == case.expected_writes,
        "answer_terms": all(term.lower() in answer.lower() for term in case.answer_terms),
    }
    if case.expected_label is not None:
        checks["classification"] = answer.strip().lower() == case.expected_label
    tool_correct = None
    if case.kind == "agent":
        tool_correct = all(
            any(c["tool"] == e.tool and subset(e.arguments, c["arguments"]) for c in calls)
            for e in case.required_tools
        ) and all(c["tool"] in case.allowed_tools for c in calls)
        checks["tool_selection"] = tool_correct
    retrieval_correct = None
    if case.expected_sources is not None:
        retrieval_correct = retrieved and (
            all(
                any(
                    h["source"] == source
                    and (case.expected_heading is None or case.expected_heading in h["heading"])
                    for h in hits
                )
                for source in case.expected_sources
            )
            if case.expected_sources
            else not hits
        )
        checks["retrieval"] = retrieval_correct
    if case.require_citation:
        used = set(re.findall(r"\[(KB-[^\]\n]+)\]", answer))
        checks["citations"] = bool(used) and used <= {h["citation"] for h in hits}
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "tool_correct": tool_correct,
        "retrieval_correct": retrieval_correct,
    }


def aggregate(rows: list[dict]) -> dict:
    def rate(values):
        values = [v for v in values if v is not None]
        return {"value": sum(values) / len(values) if values else None, "denominator": len(values)}

    times = sorted(r["wall_ms"] for r in rows)
    metrics = [r.get("metrics", {}) for r in rows if r.get("kind", "agent") == "agent"]
    complete_usage = bool(metrics) and all(m.get("token_usage_complete") for m in metrics)
    observed = [m["observed_token_usage"] for m in metrics if m.get("observed_token_usage")]
    totals = {
        k: sum(u[k] for u in observed)
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "cases": len(rows),
        "classification_accuracy": rate([r["checks"].get("classification") for r in rows]),
        "task_success_rate": rate([r["passed"] for r in rows]),
        "tool_selection_case_accuracy": rate([r.get("tool_correct") for r in rows]),
        "retrieval_hit_or_abstention_rate": rate([r.get("retrieval_correct") for r in rows]),
        "runtime_error_rate": rate([r.get("runtime_error", False) for r in rows]),
        "mean_tool_calls": mean(
            [m["tool_calls"] for m in metrics if m.get("tool_calls") is not None]
        )
        if any(m.get("tool_calls") is not None for m in metrics)
        else None,
        "mean_wall_ms": mean(times) if times else None,
        "p95_wall_ms": times[max(0, (95 * len(times) + 99) // 100 - 1)] if times else None,
        "token_usage": totals if complete_usage else None,
        "observed_token_usage": totals if observed else None,
        "usage_complete_runs": sum(bool(m.get("token_usage_complete")) for m in metrics),
    }
