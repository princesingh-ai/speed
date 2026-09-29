from fastapi import APIRouter, Depends

from app.routing.model_router import ModelRouter
from app.security.dependencies import get_current_user

router = APIRouter()
model_router = ModelRouter()


@router.get("/v1/models")
async def list_models():
    # In-process classifiers are never presented as selectable chat models.
    return {"object": "list", "data": [
        {"id": model.model_id, "object": "model", "owned_by": "speed"}
        for model in model_router.models.values() if model.kind == "llama_server"
    ]}


@router.get("/api/v1/models/health")
async def model_health(user=Depends(get_current_user)):
    return {"models": [await model_router.health(model) for model in model_router.models.values()]}
