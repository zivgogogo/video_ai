from abc import ABC, abstractmethod
from typing import AsyncIterator


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str = "",
                       output_format: str = "json") -> str:
        ...

    @abstractmethod
    async def generate_stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...
