from fastapi import APIRouter, Request

from opsmind.api.dependencies import DemoActor
from opsmind.core.errors import BusinessError
from opsmind.rag.schemas import SearchArgs
from opsmind.rag.service import KnowledgeService
from opsmind.services.tickets import get_actor

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.post("/search")
def search_knowledge(args: SearchArgs, request: Request, actor: DemoActor) -> dict:
    factory = request.app.state.session_factory
    if factory is None:
        raise BusinessError("database_unavailable", "Database is not configured.", 503)
    with factory() as session:
        get_actor(session, actor)
    return KnowledgeService(factory, request.app.state.settings).search(args)
