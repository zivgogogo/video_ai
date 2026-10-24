from typing import AsyncIterator

from openai import AsyncOpenAI

from app.ai.interface import AIProvider
from app.config import LOCAL_LLM_URL, LOCAL_LLM_API_KEY


class LocalLLMProvider(AIProvider):
    def __init__(self, model: str = "local-model"):
        self._model = model
        self._client = AsyncOpenAI(base_url=LOCAL_LLM_URL, api_key=LOCAL_LLM_API_KEY)

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=16384
        )
        return response.choices[0].message.content or ""

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=16384, stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
