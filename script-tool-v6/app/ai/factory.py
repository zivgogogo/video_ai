from typing import Optional
from app.ai.interface import AIProvider
from app.ai.claude import ClaudeProvider
from app.ai.openai import OpenAIProvider
from app.ai.deepseek import DeepSeekProvider
from app.ai.gemini import GeminiProvider
from app.ai.local import LocalLLMProvider
from app.config import AI_PROVIDER, AI_MODEL, MODEL_POOL


async def generate_with_pool_fallback(provider: AIProvider, prompt: str,
                                      system: str = "", output_format: str = "json") -> str:
    """单次调用级互备：首选 provider 失败（限流/超时等）时，依次切换模型池中其余模型重试。"""
    tried = set()
    candidates = [provider] + [create_ai_provider(model=m) for m in MODEL_POOL]
    last_err: Optional[Exception] = None
    for cand in candidates:
        key = cand.model_name()
        if key in tried:
            continue
        tried.add(key)
        try:
            return await cand.generate(prompt, system=system, output_format=output_format)
        except Exception as e:
            last_err = e
    raise last_err


def create_ai_provider(provider: Optional[str] = None, model: Optional[str] = None) -> AIProvider:
    provider = provider or AI_PROVIDER
    model = model or AI_MODEL
    # 模型池中的顶尖模型名（如 qwen3.8-max）直接作为 OpenAI 兼容后端使用
    if provider in MODEL_POOL:
        return OpenAIProvider(model=provider)
    if provider == "claude":
        return ClaudeProvider(model=model)
    elif provider == "openai":
        return OpenAIProvider(model=model)
    elif provider == "deepseek":
        return DeepSeekProvider(model=model)
    elif provider == "gemini":
        return GeminiProvider(model=model)
    elif provider == "local":
        return LocalLLMProvider(model=model)
    raise ValueError(f"Unknown AI provider: {provider}")
