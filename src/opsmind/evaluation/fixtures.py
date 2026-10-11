"""Controlled responses test plumbing only; never label them as model accuracy."""

import json

from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import FunctionCall, ToolCall, ToolTurn
from opsmind.rag.citations import sources_from_messages


class ScriptedClient:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.number = 0

    async def complete_tools(self, messages, tools):
        try:
            step = next(self.steps)
        except StopIteration:
            raise LLMError("fixture_exhausted", "Scripted response fixture exhausted.") from None
        self.number += 1
        if step.error:
            raise LLMError(step.error, "Controlled failure.")
        if step.tool:
            call = ToolCall(
                id=f"eval-{self.number}",
                type="function",
                function=FunctionCall(name=step.tool, arguments=json.dumps(step.arguments)),
            )
            return ToolTurn(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [call.model_dump(exclude={"index"})],
                },
                call,
            )
        answer = step.answer
        if "$citation" in answer:
            sources = sources_from_messages(messages)
            answer = answer.replace("$citation", "[" + next(iter(sources), "KB-missing") + "]")
        return ToolTurn({"role": "assistant", "content": answer}, None)
