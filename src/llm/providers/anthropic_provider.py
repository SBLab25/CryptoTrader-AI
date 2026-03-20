# File: src/llm/providers/anthropic_provider.py
"""
Anthropic Claude Provider
Supports: claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5, and all Claude models.
"""
import time
from typing import Optional

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20251022"


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude via the official anthropic Python SDK.
    Requires: pip install anthropic
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, config: Optional[LLMConfig] = None):
        super().__init__(model, config)
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or self.config
        client = self._get_client()
        start = time.monotonic()

        try:
            messages = [{"role": "user", "content": prompt}]
            kwargs = dict(
                model=self.model,
                max_tokens=cfg.max_tokens,
                messages=messages,
            )
            if cfg.system_prompt:
                kwargs["system"] = cfg.system_prompt

            response = await client.messages.create(**kwargs)
            content = response.content[0].text if response.content else ""
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="anthropic",
                model=self.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[Anthropic] Error: {e}")
            result = LLMResponse(
                content="", provider="anthropic", model=self.model,
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
