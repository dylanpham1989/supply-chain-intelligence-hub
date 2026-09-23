"""Hosted providers.

Imported lazily so the package is optional. The mock is the default and needs
none of this, which is what keeps a fresh clone runnable.
"""

import time

from ai.llm.base import LLMResponse, LLMUnavailableError
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

REQUEST_TIMEOUT_S = 30.0
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_HF_MODEL = "HuggingFaceH4/zephyr-7b-beta"


class AnthropicProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or settings.llm_model or DEFAULT_ANTHROPIC_MODEL
        self._api_key = api_key or settings.llm_api_key

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.1
    ) -> LLMResponse:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise LLMUnavailableError("the anthropic package is not installed") from exc

        started = time.perf_counter()
        client = AsyncAnthropic(api_key=self._api_key, timeout=REQUEST_TIMEOUT_S, max_retries=2)
        try:
            message = await client.messages.create(
                model=self._model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            log.warning("llm.failed", provider="anthropic", error=str(exc))
            raise LLMUnavailableError(str(exc)) from exc

        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=self._model,
            token_in=message.usage.input_tokens,
            token_out=message.usage.output_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


class OpenAIProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or settings.llm_model or DEFAULT_OPENAI_MODEL
        self._api_key = api_key or settings.llm_api_key

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.1
    ) -> LLMResponse:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMUnavailableError("the openai package is not installed") from exc

        started = time.perf_counter()
        client = AsyncOpenAI(api_key=self._api_key, timeout=REQUEST_TIMEOUT_S, max_retries=2)
        try:
            completion = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            log.warning("llm.failed", provider="openai", error=str(exc))
            raise LLMUnavailableError(str(exc)) from exc

        usage = completion.usage
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            model=self._model,
            token_in=usage.prompt_tokens if usage else 0,
            token_out=usage.completion_tokens if usage else 0,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


class HuggingFaceProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or settings.llm_model or DEFAULT_HF_MODEL
        self._api_key = api_key or settings.llm_api_key

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.1
    ) -> LLMResponse:
        try:
            from huggingface_hub import AsyncInferenceClient
        except ImportError as exc:
            raise LLMUnavailableError("huggingface_hub is not installed") from exc

        started = time.perf_counter()
        client = AsyncInferenceClient(token=self._api_key, timeout=REQUEST_TIMEOUT_S)
        try:
            completion = await client.chat_completion(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            log.warning("llm.failed", provider="hf", error=str(exc))
            raise LLMUnavailableError(str(exc)) from exc

        text = completion.choices[0].message.content or ""
        return LLMResponse(
            text=text,
            model=self._model,
            token_in=len(user) // 4,
            token_out=len(text) // 4,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
