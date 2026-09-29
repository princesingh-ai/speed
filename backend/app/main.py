from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import logging
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
    logger = logging.getLogger("speed")
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    from app.core.config import settings
    if settings.speed_demo_auth:
        logger.warning("SPEED demo authentication enabled; demo principal=speed-demo-admin")
    from app.api.routes.models import model_router
    for model in model_router.models.values():
        logger.info("model configured id=%s kind=%s endpoint=%s artifact=%s availability=%s",
                    model.name, model.kind, model.endpoint,
                    "present" if Path(model.model).exists() else "missing",
                    ("missing_artifact" if not Path(model.model).exists() else "not_loaded")
                    if model.kind == "in_process" else "not_probed")
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
