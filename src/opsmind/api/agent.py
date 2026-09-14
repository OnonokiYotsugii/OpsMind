import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Path, Request

from opsmind.agent.runtime import AgentRuntime
from opsmind.agent.store import AgentStore
from opsmind.api.dependencies import DemoActor
from opsmind.core.errors import BusinessError
from opsmind.llm.client import OpenAICompatibleClient
from opsmind.schemas.agent import Decision, RunCreate, RunRead

router = APIRouter(prefix="/api/v1/agent/runs", tags=["agent"])
RunId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


def get_store(request: Request) -> AgentStore:
    factory = request.app.state.session_factory
    if factory is None:
        raise BusinessError("database_unavailable", "Agent requires a configured database.", 503)
    return AgentStore(factory, request.app.state.settings)


async def get_runtime(request: Request, store: Annotated[AgentStore, Depends(get_store)]):
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        yield AgentRuntime(store, OpenAICompatibleClient(request.app.state.settings, http))


@router.post("", response_model=RunRead, status_code=201)
async def create_run(
    data: RunCreate,
    actor: DemoActor,
    runtime: Annotated[AgentRuntime, Depends(get_runtime)],
) -> RunRead:
    return await runtime.create(data.message, actor)


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: RunId,
    actor: DemoActor,
    store: Annotated[AgentStore, Depends(get_store)],
) -> RunRead:
    return await asyncio.to_thread(store.get, run_id, actor)


@router.post("/{run_id}/decisions", response_model=RunRead)
async def decide_run(
    run_id: RunId,
    data: Decision,
    actor: DemoActor,
    runtime: Annotated[AgentRuntime, Depends(get_runtime)],
) -> RunRead:
    return await runtime.decide(run_id, actor, data.action_id, data.approved)
