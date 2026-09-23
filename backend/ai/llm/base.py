from dataclasses import dataclass
from typing import Protocol


class LLMUnavailableError(Exception):
    """The provider could not answer. Never surfaced as a 500."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    token_in: int
    token_out: int
    latency_ms: int


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.1
    ) -> LLMResponse: ...
