"""LLM decides tools; deterministic code enforces budgets and approval boundaries."""

import asyncio
import time

from sqlalchemy.exc import SQLAlchemyError

from opsmind.agent.store import AgentStore
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import ToolClient
from opsmind.schemas.agent import RunRead
from opsmind.tools.registry import TOOLS


class AgentRuntime:
    def __init__(self, store: AgentStore, client: ToolClient):
        self.store = store
        self.client = client

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
                async with asyncio.timeout(remaining_ms / 1000):
                    turn = await self.client.complete_tools(messages, declarations)
                run = await asyncio.to_thread(
                    self.store.apply,
                    run_id,
                    actor,
                    turn,
                    max(1, round((time.monotonic() - started) * 1000)),
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
