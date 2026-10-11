"""Local P1 demo app. Importing the module does not connect to MySQL."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from opsmind.api.agent import router as agent_router
from opsmind.api.analysis import router as analysis_router
from opsmind.api.errors import install_error_handlers
from opsmind.api.knowledge import router as knowledge_router
from opsmind.api.routes import router
from opsmind.core.config import Settings
from opsmind.core.logging import configure_logging
from opsmind.db.session import create_db_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.environment == "production":
        raise ValueError("P1 uses a local demo identity; production mode is not supported.")
    configure_logging(settings)
    raw_url = settings.database_url.get_secret_value()
    engine = create_db_engine(raw_url) if raw_url else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="OpsMind",
        version="0.1.0",
        lifespan=lifespan,
        description="Local maintenance Agent demo with human approval; no production login.",
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False) if engine else None

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness only; does not claim database readiness."""
        return {"status": "ok"}

    web = Path(__file__).parent / "web"

    @app.get("/", include_in_schema=False)
    def workspace() -> FileResponse:
        return FileResponse(web / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/assets", StaticFiles(directory=web), name="assets")

    install_error_handlers(app)
    app.include_router(router)
    app.include_router(analysis_router)
    app.include_router(agent_router)
    app.include_router(knowledge_router)
    return app
