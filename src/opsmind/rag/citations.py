"""Validate identifiers, not semantic correctness of generated claims."""

import json
import re


def sources_from_messages(messages: list[dict]) -> dict:
    sources = {}
    for message in messages:
        if message.get("role") != "tool":
            continue
        payload = json.loads(message["content"])
        data = payload.get("data")
        if isinstance(data, dict):
            for item in data.get("items", []):
                if isinstance(item, dict) and "citation" in item:
                    sources[item["citation"]] = item
    return sources


def checked_answer(answer: str, messages: list[dict]) -> str:
    sources = sources_from_messages(messages)
    used = set(re.findall(r"\[(KB-[^\]\n]+)\]", answer))
    if used - sources.keys() or (sources and not used):
        return (
            "知识库回答未通过来源编号校验，不能作为有依据的诊断。"
            "请重新提问或直接查看知识库检索结果。"
        )
    if not used:
        return answer
    lines = [answer, "\n参考来源（程序核对编号，内容仍需人工判断）："]
    for key in sorted(used):
        item = sources[key]
        lines.append(
            f"[{key}] {item['title']} / {item['source']} / v{item['version']} / 第{item['line']}行"
        )
    return "\n".join(lines)
