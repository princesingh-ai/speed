from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.api.routes.auth import router as auth_router
from app.api.routes.security import router as security_router
from app.api.routes.permissions import router as permissions_router
from app.api.routes.tasks import router as tasks_router
from app.tools.builtin.register import register_builtin_tools
from app.api.routes.tools import router as tools_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="SPEED",
        description="Sovereign local AI agent platform",
        version="0.1.0",
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


    return app


app = create_app()