from typing import AsyncIterator

from openai import AsyncOpenAI

from app.ai.interface import AIProvider
from app.config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekProvider(AIProvider):
    def __init__(self, model: str = ""):
        self._model = model or DEEPSEEK_MODEL
        self._client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY or "not-configured",
            base_url=DEEPSEEK_BASE_URL,
        )

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = []
        if system:
            if "json" not in system.lower():
                system += " Output valid JSON only, no markdown wrapping."
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 16384,
        }
        if output_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
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
