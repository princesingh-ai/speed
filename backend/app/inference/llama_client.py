import httpx


class LlamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Local inference must not inherit an external HTTP proxy from the host.
        self.client = httpx.AsyncClient(timeout=120.0, trust_env=False)

    async def chat(
        self,
        messages: list[dict],
        model: str = "",
        conversation_id: str | None = None,
    ) -> dict:

        payload = {
            "messages": messages,
            "stream": False,
        }

        if model:
            payload["model"] = model

        headers = {}

        if conversation_id:
            headers["X-Conversation-Id"] = conversation_id

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )

        response.raise_for_status()

        return response.json()

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = "",
        conversation_id: str | None = None,
    ):
        payload = {
            "messages": messages,
            "stream": True,
        }

        if model:
            payload["model"] = model

        headers = {}

        if conversation_id:
            headers["X-Conversation-Id"] = conversation_id

        async with self.client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        ) as response:

            response.raise_for_status()

            async for chunk in response.aiter_bytes():
                yield chunk

    async def close(self) -> None:
        await self.client.aclose()
