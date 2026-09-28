from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from app.api.routes.agent import router as agent_router
from app.orchestration.service import AgentService

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.api.routes.auth import router as auth_router
from app.api.routes.security import router as security_router
from app.api.routes.permissions import router as permissions_router
from app.api.routes.tasks import router as tasks_router
from app.tools.builtin.register import register_builtin_tools
from app.api.routes.tools import router as tools_router

@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        await app.state.agent.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SPEED",
        description="Sovereign local AI agent platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(models_router)
    app.include_router(auth_router)
    app.include_router(security_router)
    app.include_router(permissions_router)
    app.include_router(tasks_router)
    register_builtin_tools()
    app.include_router(tools_router)
    app.state.agent = AgentService()
    app.state.ws_tickets = {}
    app.include_router(agent_router)
    app.mount("/phase1", StaticFiles(directory=Path(__file__).parent / "static" / "phase1", html=True), name="phase1")


    return app


app = create_app()
