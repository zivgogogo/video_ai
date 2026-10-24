from typing import AsyncIterator

from anthropic import AsyncAnthropic

from app.ai.interface import AIProvider
from app.config import ANTHROPIC_API_KEY


class ClaudeProvider(AIProvider):
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self._model = model
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY or "not-configured")

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": self._model, "max_tokens": 8192, "messages": messages}
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        if response.content and response.content[0].type == "text":
            return response.content[0].text
        return ""

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": self._model, "max_tokens": 8192, "messages": messages}
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
