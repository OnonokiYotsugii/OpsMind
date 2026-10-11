import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from opsmind.core.config import Settings
from opsmind.evaluation.dataset import Case, load_cases
from opsmind.evaluation.runner import test_url as evaluation_url
from opsmind.evaluation.scoring import aggregate, grade
from opsmind.llm.telemetry import response_metadata
from opsmind.observability.trace import metrics, project_events


def sample_case(**changes):
    data = {
        "id": "test",
        "category": "equipment",
        "prompt": "query",
        "required_tools": [{"tool": "get_equipment", "arguments": {"equipment_no": "EQ-1"}}],
        "allowed_tools": ["get_equipment"],
        "answer_terms": ["EQ-1"],
    }
    return Case.model_validate({**data, **changes})


def good_grade(case=None, **changes):
    values = dict(
        case=case or sample_case(),
        status="completed",
        answer="EQ-1",
        calls=[{"tool": "get_equipment", "arguments": {"equipment_no": "EQ-1"}}],
        hits=[],
        retrieved=False,
        writes=0,
        error=None,
    )
    return grade(**{**values, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed"},
        {"error": "llm_timeout"},
        {"writes": 1},
        {"answer": "wrong"},
        {"calls": []},
        {"calls": [{"tool": "get_equipment", "arguments": {"equipment_no": "EQ-WRONG"}}]},
        {"calls": [{"tool": "delete_all", "arguments": {}}]},
    ],
)
def test_bad_results_do_not_pass(changes):
    assert not good_grade(**changes)["passed"]


def test_order_is_not_required_but_arguments_are():
    case = sample_case(required_tools=[{"tool": "a"}, {"tool": "b"}], allowed_tools=["a", "b"])
    assert good_grade(case, calls=[{"tool": "b", "arguments": {}}, {"tool": "a", "arguments": {}}])[
        "passed"
    ]


def test_classification_requires_exact_label():
    case = sample_case(expected_label="electrical", answer_terms=[])
    assert good_grade(case, answer="electrical")["passed"]
    assert not good_grade(case, answer="not electrical")["passed"]


def test_empty_retrieval_requires_actual_search():
    case = sample_case(expected_sources=[])
    assert not good_grade(case)["passed"]
    assert good_grade(case, retrieved=True)["passed"]


def test_citation_and_retrieval_labels():
    case = sample_case(expected_sources=["manual"], expected_heading="E102", require_citation=True)
    hit = {"source": "manual", "heading": "E102", "citation": "KB-a"}
    assert good_grade(case, retrieved=True, hits=[hit], answer="EQ-1 [KB-a]")["passed"]
    assert not good_grade(case, retrieved=True, hits=[hit], answer="EQ-1 [KB-fake]")["passed"]
    assert not good_grade(
        case, retrieved=True, hits=[{**hit, "source": "wrong"}], answer="EQ-1 [KB-a]"
    )["passed"]


def test_write_requires_observed_effect_and_success_receipt():
    case = sample_case(approval="approve", expected_writes=1)
    assert not good_grade(case, writes=1)["passed"]
    assert good_grade(case, writes=1, successful_writes=1)["passed"]


def test_empty_aggregate_is_unknown():
    summary = aggregate([])
    assert summary["task_success_rate"] == {"value": None, "denominator": 0}
    assert summary["token_usage"] is None and summary["mean_wall_ms"] is None


def test_aggregate_denominators_and_expected_errors():
    rows = [
        dict(
            id="a",
            kind="agent",
            passed=True,
            checks={},
            tool_correct=True,
            retrieval_correct=None,
            runtime_error=False,
            wall_ms=10,
            metrics={"tool_calls": 2},
        ),
        dict(
            id="b",
            kind="agent",
            passed=True,
            checks={},
            tool_correct=True,
            retrieval_correct=None,
            runtime_error=True,
            wall_ms=30,
            metrics={"tool_calls": 0},
        ),
        dict(
            id="c",
            kind="retrieval",
            passed=False,
            checks={},
            tool_correct=None,
            retrieval_correct=False,
            runtime_error=False,
            wall_ms=20,
            metrics={},
        ),
    ]
    summary = aggregate(rows)
    assert summary["task_success_rate"]["value"] == 2 / 3
    assert summary["runtime_error_rate"]["value"] == 1 / 3
    assert summary["tool_selection_case_accuracy"]["denominator"] == 2
    assert summary["retrieval_hit_or_abstention_rate"]["denominator"] == 1
    assert summary["mean_tool_calls"] == 1 and summary["p95_wall_ms"] == 30


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 9},
    ],
)
def test_invalid_usage_is_unknown(usage):
    assert response_metadata({"usage": usage})["usage"] is None


def test_trace_usage_coverage_retry_and_incomplete_calls():
    events = [
        {"kind": "started", "trace_version": 1},
        {"kind": "model_step", "step": 1},
        {"kind": "model_start", "trace_id": "a"},
        {
            "kind": "model_end",
            "trace_id": "a",
            "ok": True,
            "duration_ms": 10,
            "attempts": 1,
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        },
    ]
    assert metrics(events)["token_usage"]["total_tokens"] == 5
    assert metrics(events[1:])["token_usage"] is None
    assert metrics([e for e in events if e["kind"] != "model_step"])["token_usage"] is None
    events[-1]["attempts"] = 2
    assert metrics(events)["token_usage"] is None
    assert metrics(events)["observed_token_usage"]["total_tokens"] == 5
    events.append({"kind": "model_start", "trace_id": "lost"})
    assert metrics(events)["model_calls_without_end"] == 1
    assert metrics([])["coverage"] == "legacy_partial"
    assert metrics([])["tool_calls"] is None


def test_trace_excludes_business_bodies():
    events = [
        {
            "kind": "decision",
            "arguments": {"secret": "sentinel"},
            "result": {"text": "sentinel"},
            "messages": ["sentinel"],
            "action_id": "abc",
        }
    ]
    assert "sentinel" not in json.dumps(project_events(events))


def test_dataset_is_strict_and_versioned(tmp_path):
    path = Path("evaluation/cases.v1.jsonl")
    cases = load_cases(path)
    assert len(cases) == 18 and len({c.category for c in cases}) == 7
    bad = tmp_path / "bad.jsonl"
    row = cases[0].model_dump_json()
    bad.write_text(row + "\n" + row, encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_cases(bad)
    with pytest.raises(ValidationError):
        sample_case(execute_shell="bad")


@pytest.mark.parametrize(
    "url",
    ["mysql+pymysql://u:p@127.0.0.1/opsmind_dev", "mysql+pymysql://u:p@example.com/opsmind_test"],
)
def test_evaluation_rejects_nonlocal_or_business_database(url):
    with pytest.raises(ValueError, match="opsmind_test"):
        evaluation_url(Settings(_env_file=None, test_database_url=url))


def test_evaluation_rejects_database_alias():
    url = "mysql+pymysql://u:p@127.0.0.1/opsmind_test"
    with pytest.raises(ValueError, match="differ"):
        evaluation_url(Settings(_env_file=None, test_database_url=url, database_url=url))
