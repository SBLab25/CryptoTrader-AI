# File: src/llm/providers/groq_provider.py
"""
Groq Provider
Supports: llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768,
          gemma2-9b-it, and all models available on Groq Cloud.
Groq is extremely fast (100-500 tokens/sec) — ideal for real-time trading signals.
"""
import time
from typing import Optional

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(BaseLLMProvider):
    """
    Groq Cloud via the groq Python SDK (OpenAI-compatible interface).
    Requires: pip install groq
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, config: Optional[LLMConfig] = None):
        super().__init__(model, config)
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=self._api_key)
            except ImportError:
                raise ImportError("groq package not installed. Run: pip install groq")
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
                provider="groq",
                model=self.model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[Groq] Error: {e}")
            result = LLMResponse(
                content="", provider="groq", model=self.model,
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
