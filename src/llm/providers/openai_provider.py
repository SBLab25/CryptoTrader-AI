# File: src/llm/providers/openai_provider.py
"""
OpenAI Provider
Supports: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo, and all OpenAI chat models.
"""
import time
from typing import Optional

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI via the official openai Python SDK.
    Requires: pip install openai
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, config: Optional[LLMConfig] = None):
        super().__init__(model, config)
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or self.config
        client = self._get_client()
        start = time.monotonic()

        try:
            messages = []
            if cfg.system_prompt:
                messages.append({"role": "system", "content": cfg.system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
            )
            content = response.choices[0].message.content or ""
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="openai",
                model=self.model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[OpenAI] Error: {e}")
            result = LLMResponse(
                content="", provider="openai", model=self.model,
                latency_ms=round(latency, 1), error=str(e),
            )

        self._record(result)
        return result

    async def health_check(self) -> bool:
        try:
            r = await self.complete("Say OK", LLMConfig(max_tokens=5))
            return r.success
        except Exception:
            return False
