from typing import AsyncIterator

from google import genai
from google.genai import types

from app.ai.interface import AIProvider
from app.config import GEMINI_API_KEY, GEMINI_MODEL


class GeminiProvider(AIProvider):
    def __init__(self, model: str = ""):
        self._model = model or GEMINI_MODEL
        self._client = genai.Client(api_key=GEMINI_API_KEY or "not-configured")

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        config = types.GenerateContentConfig(
            max_output_tokens=8192,
        )
        if system:
            if "json" not in system.lower():
                system += " Output valid JSON only, no markdown wrapping."
            config.system_instruction = system

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        if response.text:
            return response.text
        return ""

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        config = types.GenerateContentConfig(
            max_output_tokens=8192,
        )
        if system:
            config.system_instruction = system

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=config,
        ):
            if chunk.text:
                yield chunk.text
