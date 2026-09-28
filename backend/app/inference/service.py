from app.inference.llama_client import LlamaClient
from app.routing.models import ModelConfig


class InferenceService:

    async def chat(
        self,
        messages: list[dict],
        model: ModelConfig,
        conversation_id: str | None = None,
    ) -> dict:

        client = LlamaClient(
            base_url=model.endpoint,
        )

        try:
            return await client.chat(
                messages=messages,
                model=model.model,
                conversation_id=conversation_id,
            )
        finally:
            await client.close()

    async def chat_stream(
        self,
        messages: list[dict],
        model: ModelConfig,
        conversation_id: str | None = None,
    ):
        client = LlamaClient(
            base_url=model.endpoint,
        )

        try:
            async for chunk in client.chat_stream(
                messages=messages,
                model=model.model,
                conversation_id=conversation_id,
            ):
                yield chunk

        finally:
            await client.close()