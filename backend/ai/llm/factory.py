from ai.llm.base import LLMProvider
from ai.llm.mock import MockProvider
from app.core.config import settings


def get_llm(provider: str | None = None) -> LLMProvider:
    name = provider or settings.llm_provider
    if name == "mock":
        return MockProvider()

    from ai.llm.providers import AnthropicProvider, HuggingFaceProvider, OpenAIProvider

    match name:
        case "anthropic":
            return AnthropicProvider()
        case "openai":
            return OpenAIProvider()
        case "hf":
            return HuggingFaceProvider()
        case _:
            raise ValueError(f"unknown llm provider {name!r}")
