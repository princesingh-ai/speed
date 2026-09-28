from fastapi import APIRouter

from app.routing.model_router import ModelRouter

router = APIRouter()
model_router = ModelRouter()

@router.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": model.model, "object": "model", "owned_by": "speed"}for model in model_router.models.values()]}