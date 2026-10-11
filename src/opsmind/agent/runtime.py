"""LangGraph execution facade; MySQL remains the authority for business effects."""

import asyncio
from uuid import uuid4

from langgraph.types import Command

from opsmind.agent.checkpointer import MySQLSaver
from opsmind.agent.execution import run_owner
from opsmind.agent.graph import build_graph
from opsmind.agent.store import AgentStore
from opsmind.llm.errors import LLMError
from opsmind.llm.tool_protocol import ToolClient
from opsmind.rag.service import KnowledgeService
from opsmind.schemas.agent import RunRead


class AgentRuntime:
    def __init__(self, store: AgentStore, client: ToolClient):
        self.store = store
        self.client = client
        self.knowledge = KnowledgeService(store.factory, store.settings)
        self.saver = MySQLSaver(store.factory)
        self.graph = build_graph(self, self.saver)

    async def offload(self, function, *args):
        # LangGraph may save pending writes alongside the next node. Serialize short
        # local DB work with saver IO, including test factories sharing one connection.
        def invoke():
            with self.saver.lock:
                return function(*args)

        return await asyncio.to_thread(invoke)

    async def create(self, message: str, actor: str) -> RunRead:
        run = await self.offload(self.store.create, message, actor)
        return await self.drive(run.id, actor)

    async def decide(self, run_id: str, actor: str, action_id: str, approved: bool) -> RunRead:
        return await self._execute(run_id, actor, {"action_id": action_id, "approved": approved})

    async def drive(self, run_id: str, actor: str) -> RunRead:
        return await self._execute(run_id, actor)

    async def _execute(self, run_id: str, actor: str, decision: dict | None = None) -> RunRead:
        owner = uuid4().hex
        await self.offload(self.store.claim, run_id, actor, owner)
        token = run_owner.set(owner)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 150}
        try:
            if decision:
                run = await self.offload(
                    self.store.validate_decision,
                    run_id,
                    actor,
                    decision["action_id"],
                    decision["approved"],
                )
            else:
                run = await self.offload(self.store.get, run_id, actor)
            if run.status not in {"running", "waiting_confirmation"}:
                return run
            if (
                decision
                and run.status == "waiting_confirmation"
                and any(
                    e["kind"] == "decision" and e["action_id"] == decision["action_id"]
                    for e in run.events
                )
            ):
                return run  # Replaying an old receipt cannot approve a newer action.
            # Config permits at most 300 seconds of model/tool work. Leave DB IO margin,
            # but always finish before the 420-second execution lease can be reclaimed.
            async with asyncio.timeout(330):
                checkpoint = await self.saver.aget_tuple(config)
                if checkpoint is None:
                    await self.graph.ainvoke(
                        {"run_id": run_id, "actor": actor}, config, durability="sync"
                    )
                elif not decision:
                    await self.graph.ainvoke(None, config, durability="sync")
                if decision:
                    # Reach an interrupt if a process died between proposing and pausing.
                    state = await self.graph.aget_state(config)
                    if state.next and not any(t.interrupts for t in state.tasks):
                        await self.graph.ainvoke(None, config, durability="sync")
                    await self.graph.ainvoke(Command(resume=decision), config, durability="sync")
            return await self.offload(self.store.get, run_id, actor)
        except TimeoutError:
            return await self.offload(self.store.mark_failed, run_id, actor, "agent_timeout")
        except LLMError as exc:
            return await self.offload(self.store.mark_failed, run_id, actor, exc.code)
        finally:
            try:
                await self.offload(self.store.release, run_id, owner)
            finally:
                run_owner.reset(token)
