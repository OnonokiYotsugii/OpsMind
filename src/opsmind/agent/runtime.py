"""LLM decides tools; deterministic code enforces budgets and approval boundaries."""

import asyncio
import time

from sqlalchemy.exc import SQLAlchemyError

from opsmind.agent.store import AgentStore
from opsmind.core.errors import BusinessError
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import ToolClient
from opsmind.rag.service import KnowledgeService
from opsmind.schemas.agent import RunRead
from opsmind.tools.registry import TOOLS, validate_call


class AgentRuntime:
    def __init__(self, store: AgentStore, client: ToolClient):
        self.store = store
        self.client = client
        self.knowledge = KnowledgeService(store.factory, store.settings)

    async def create(self, message: str, actor: str) -> RunRead:
        run = await asyncio.to_thread(self.store.create, message, actor)
        return await self.drive(run.id, actor)

    async def decide(self, run_id: str, actor: str, action_id: str, approved: bool) -> RunRead:
        run, continue_run = await asyncio.to_thread(
            self.store.decide,
            run_id,
            actor,
            action_id,
            approved,
        )
        return await self.drive(run_id, actor) if continue_run else run

    async def drive(self, run_id: str, actor: str) -> RunRead:
        declarations = [tool.declaration() for tool in TOOLS.values()]
        try:
            while True:
                context = await asyncio.to_thread(self.store.reserve_step, run_id, actor)
                if context is None:
                    return await asyncio.to_thread(self.store.get, run_id, actor)
                messages, remaining_ms = context
                started = time.monotonic()
                try:
                    async with asyncio.timeout(remaining_ms / 1000):
                        turn = await self.client.complete_tools(messages, declarations)
                except LLMError as exc:
                    if exc.code != "llm_multiple_tool_calls":
                        raise
                    await asyncio.to_thread(
                        self.store.correct_multiple_calls,
                        run_id,
                        actor,
                        max(1, round((time.monotonic() - started) * 1000)),
                    )
                    continue
                knowledge_result = None
                if (
                    turn.call
                    and turn.call.function.name == "search_knowledge"
                    and await asyncio.to_thread(self.store.may_search, run_id, actor, turn.call.id)
                ):
                    try:
                        _, params = validate_call(
                            turn.call.function.name, turn.call.function.arguments
                        )
                        remaining = remaining_ms / 1000 - (time.monotonic() - started)
                        async with asyncio.timeout(max(0, remaining)):
                            data = await asyncio.to_thread(self.knowledge.search, params)
                        knowledge_result = {"ok": True, "data": data}
                    except BusinessError as exc:
                        knowledge_result = {"ok": False, "error": exc.code, "message": exc.message}
                run = await asyncio.to_thread(
                    self.store.apply,
                    run_id,
                    actor,
                    turn,
                    max(1, round((time.monotonic() - started) * 1000)),
                    knowledge_result,
                )
                if run.status != "running":
                    return run
        except TimeoutError:
            return await asyncio.to_thread(self.store.mark_failed, run_id, actor, "agent_timeout")
        except LLMError as exc:
            return await asyncio.to_thread(self.store.mark_failed, run_id, actor, exc.code)
        except SQLAlchemyError:
            # May itself fail if MySQL is fully unavailable; API returns a safe 503 then.
            return await asyncio.to_thread(
                self.store.mark_failed,
                run_id,
                actor,
                "agent_database_error",
            )
