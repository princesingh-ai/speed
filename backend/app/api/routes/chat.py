from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatCompletionRequest
from app.inference.service import InferenceService
from app.routing.service import RoutingService


router = APIRouter()

routing_service = RoutingService()
inference_service = InferenceService()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    x_conversation_id: str | None = Header(
        default=None,
        alias="X-Conversation-Id",
    ),
):

    messages = [
        message.model_dump()
        for message in request.messages
    ]

    user_message = next(
        (
            message["content"]
            for message in reversed(messages)
            if message["role"] == "user"
        ),
        "",
    )

    analysis, model = routing_service.route(user_message)

    if model is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_UNAVAILABLE",
                "task_type": analysis.task_type.value,
                "message": (
                    f"No model is currently available for "
                    f"{analysis.task_type.value} tasks."
                ),
            },
        )

    if request.stream:
        return StreamingResponse(
            inference_service.chat_stream(
                messages=messages,
                model=model,
                conversation_id=x_conversation_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    response = await inference_service.chat(
        messages=messages,
        model=model,
        conversation_id=x_conversation_id,
    )

    return response