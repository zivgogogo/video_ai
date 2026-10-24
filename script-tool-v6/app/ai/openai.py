from typing import AsyncIterator

from openai import AsyncOpenAI

from app.ai.interface import AIProvider
from app.config import OPENAI_API_KEY, OPENAI_BASE_URL


class OpenAIProvider(AIProvider):
    def __init__(self, model: str = "gpt-4o"):
        self._model = model
        kwargs = {"api_key": OPENAI_API_KEY or "not-configured"}
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        # 超时与重试策略：单模型 150s 封顶、不在 SDK 层重试。
        # 原因：generate_with_pool_fallback 已提供模型池轮转互备，SDK 层再重试
        # 会把“单模型响应慢”放大成数倍等待（旧值 timeout=600 + max_retries=1
        # 配合 3 个模型的池，最坏可让界面卡等近 1 小时，表现为按钮一直转圈）。
        self._client = AsyncOpenAI(**kwargs, timeout=150.0, max_retries=0)

    def model_name(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        messages = []
        if system:
            # 确保 prompt 包含 "JSON" 关键字（DeepSeek 等 API 要求）
            if "json" not in system.lower():
                system += " Output valid JSON only, no markdown wrapping."
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self._model,
            "messages": messages,
            # 分镜等长 JSON 输出在 8192 下会被拦腰截断（JSON 不完整→解析失败），
            # 提高到 16384 以容纳 10+ 镜头的完整结构。
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
