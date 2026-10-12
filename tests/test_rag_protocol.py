import json

import pytest
from pydantic import ValidationError

from opsmind.rag.chunking import split_document
from opsmind.rag.citations import checked_answer
from opsmind.rag.schemas import SearchArgs
from opsmind.tools.registry import Risk, validate_call


def test_chunk_locations_and_headings():
    chunks = split_document("# 标题\n\n" + "报警" * 130 + "\n\n## 后续\n记录结果")
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[0].heading == "标题" and chunks[0].line == 3
    assert chunks[-1].heading == "后续" and chunks[-1].line == 6
    assert "".join(c.text for c in chunks[:-1]).strip() == "报警" * 130


def test_blank_document():
    assert split_document("# 空标题\n\n") == []


@pytest.mark.parametrize(
    "args",
    [
        {"query": " "},
        {"query": "x", "limit": True},
        {"query": "x", "limit": 6},
        {"query": "x", "approved": True},
    ],
)
def test_search_arguments(args):
    with pytest.raises(ValidationError):
        SearchArgs(**args)


def test_readonly_tool_registration():
    definition, params = validate_call("search_knowledge", '{"query":" E102 "}')
    assert definition.risk == Risk.LOW and params.query == "E102"


def source_messages():
    return [
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "ok": True,
                    "data": {
                        "items": [
                            {
                                "citation": "KB-abc-1",
                                "title": "手册",
                                "source": "demo",
                                "version": "1",
                                "line": 7,
                            }
                        ]
                    },
                }
            ),
        }
    ]


def test_citation_is_verified_and_resolved():
    answer = checked_answer("可能为供电异常 [KB-abc-1]", source_messages())
    assert "第7行" in answer and "可能为供电异常" in answer


@pytest.mark.parametrize("answer", ["供电异常", "供电异常 [KB-fake]"])
def test_missing_or_invented_citation_is_replaced(answer):
    assert "未通过" in checked_answer(answer, source_messages())


def test_non_rag_answer_unchanged():
    assert checked_answer("设备运行中", []) == "设备运行中"


def test_fabricated_citation_without_search_is_rejected():
    assert "未通过" in checked_answer("参考 [KB-fake]", [])


def test_placeholder_in_abstention_is_not_a_fabricated_source():
    answer = "未检索到资料，没有可引用的 [KB-...] 编号，依据不足。"
    assert checked_answer(answer, []) == answer
    assert "未通过" in checked_answer(answer + " 参考 [KB-fake]", [])
    assert "未通过" in checked_answer(answer, source_messages())


@pytest.mark.parametrize(
    "query, heading, expected",
    [
        ("DEMO-24V E102 报警含义 排查", "DEMO-24V：E102 供电报警", True),
        ("demo-24v e102 报警码", "DEMO-24V：E102 供电报警", True),
        ("DEMO-24V E102", "DEMO-24V：E205 温度报警", False),
        ("OTHER-24V E102", "DEMO-24V：E102 供电报警", False),
        ("DEMO-24V E1020", "DEMO-24V：E102 供电报警", False),
        ("E102 报警", "DEMO-24V：E102 供电报警", False),
        ("草莓蛋糕", "DEMO-24V：E102 供电报警", False),
    ],
)
def test_exact_alarm_heading_requires_full_model_and_code(query, heading, expected):
    from opsmind.rag.service import exact_alarm_heading

    assert exact_alarm_heading(query, heading) is expected
