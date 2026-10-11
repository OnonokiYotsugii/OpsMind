"""Graph nodes reuse the existing business transaction and approval services."""

import asyncio
import time
from uuid import uuid4

from langgraph.types import interrupt

from opsmind.agent.graph_state import GraphState
from opsmind.core.errors import BusinessError
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import ToolCall, ToolTurn
from opsmind.schemas.agent import Decision
from opsmind.tools.registry import TOOLS, validate_call


class GraphNodes:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store = runtime.store

    async def sync(self, state: GraphState) -> dict:
        run = await self.runtime.offload(self.store.get, state["run_id"], state["actor"])
        return {"status": run.status, "action": run.pending_action}

    async def model(self, state: GraphState) -> dict:
        context = await self.runtime.offload(
            self.store.reserve_step, state["run_id"], state["actor"]
        )
        if context is None:
            return await self.sync(state)
        messages, remaining_ms = context
        trace_id = uuid4().hex
        await self.runtime.offload(
            self.store.record_model, state["run_id"], state["actor"], "model_start", trace_id, {}
        )
        started = time.monotonic()
        try:
            async with asyncio.timeout(remaining_ms / 1000):
                turn = await self.runtime.client.complete_tools(
                    messages, [t.declaration() for t in TOOLS.values()]
                )
        except (LLMError, TimeoutError) as exc:
            await self.runtime.offload(
                self.store.record_model,
                state["run_id"],
                state["actor"],
                "model_end",
                trace_id,
                {
                    "ok": False,
                    "code": getattr(exc, "code", "agent_timeout"),
                    "duration_ms": max(1, round((time.monotonic() - started) * 1000)),
                    **(getattr(exc, "telemetry", None) or {}),
                },
            )
            if not isinstance(exc, LLMError) or exc.code != "llm_multiple_tool_calls":
                raise
            await self.runtime.offload(
                self.store.correct_multiple_calls,
                state["run_id"],
                state["actor"],
                max(1, round((time.monotonic() - started) * 1000)),
            )
            return {"status": "running", "turn": None}
        await self.runtime.offload(
            self.store.record_model,
            state["run_id"],
            state["actor"],
            "model_end",
            trace_id,
            {
                "ok": True,
                "duration_ms": max(1, round((time.monotonic() - started) * 1000)),
                **(turn.telemetry or {}),
            },
        )
        return {
            "status": "apply",
            "turn": {
                "message": turn.message,
                "call": turn.call.model_dump() if turn.call else None,
            },
            "elapsed_ms": max(1, round((time.monotonic() - started) * 1000)),
            "effect_id": uuid4().hex,
        }

    async def apply(self, state: GraphState) -> dict:
        saved = state["turn"]
        turn = ToolTurn(
            saved["message"], ToolCall.model_validate(saved["call"]) if saved["call"] else None
        )
        knowledge_result = None
        elapsed = state["elapsed_ms"]
        knowledge_ms = 0
        if (
            turn.call
            and turn.call.function.name == "search_knowledge"
            and await self.runtime.offload(
                self.store.may_search, state["run_id"], state["actor"], turn.call.id
            )
        ):
            started = time.monotonic()
            try:
                _, params = validate_call(turn.call.function.name, turn.call.function.arguments)
                remaining = await self.runtime.offload(
                    self.store.remaining_budget, state["run_id"], state["actor"]
                )
                async with asyncio.timeout(max(0, (remaining - elapsed) / 1000)):
                    data = await self.runtime.offload(self.runtime.knowledge.search, params)
                knowledge_result = {"ok": True, "data": data}
            except BusinessError as exc:
                knowledge_result = {"ok": False, "error": exc.code, "message": exc.message}
            knowledge_ms = max(1, round((time.monotonic() - started) * 1000))
            elapsed += knowledge_ms
        run = await self.runtime.offload(
            self.store.apply,
            state["run_id"],
            state["actor"],
            turn,
            elapsed,
            knowledge_result,
            state["effect_id"],
            knowledge_ms,
        )
        return {"status": run.status, "action": run.pending_action, "turn": None}

    async def approval(self, state: GraphState) -> dict:
        action = state["action"]
        run = await self.runtime.offload(self.store.get, state["run_id"], state["actor"])
        receipt = next(
            (
                e
                for e in run.events
                if e["kind"] == "decision" and e["action_id"] == action["action_id"]
            ),
            None,
        )
        if receipt:
            # Crash after business commit but before checkpoint: use the durable receipt.
            return {"status": run.status, "action": run.pending_action}
        if run.status != "waiting_confirmation":
            return {"status": run.status, "action": run.pending_action}
        decision = Decision.model_validate(interrupt(action))
        if decision.action_id != action["action_id"]:
            raise BusinessError(
                "action_mismatch", "Confirmation does not match the pending action."
            )
        run, _ = await self.runtime.offload(
            self.store.decide,
            state["run_id"],
            state["actor"],
            decision.action_id,
            decision.approved,
        )
        return {"status": run.status, "action": run.pending_action}
