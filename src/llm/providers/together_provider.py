# File: src/llm/providers/together_provider.py
"""
Together AI Provider
Supports 100+ open-source models:
  - meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
  - mistralai/Mixtral-8x22B-Instruct-v0.1
  - Qwen/Qwen2.5-72B-Instruct-Turbo
  - deepseek-ai/DeepSeek-V3
  - google/gemma-2-27b-it
  - NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO
See full list: https://api.together.ai/models
"""
import time
from typing import Optional

import aiohttp

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
BASE_URL = "https://api.together.xyz/v1"


class TogetherProvider(BaseLLMProvider):
    """
    Together AI via OpenAI-compatible REST API.
    Get key: https://api.together.ai/
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, config: Optional[LLMConfig] = None):
        super().__init__(model, config)
        self._api_key = api_key

    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or self.config
        start = time.monotonic()

        messages = []
        if cfg.system_prompt:
            messages.append({"role": "system", "content": cfg.system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=cfg.timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Together HTTP {resp.status}: {body[:300]}")
                    data = await resp.json()

            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="together",
                model=self.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[Together] Error: {e}")
            result = LLMResponse(
                content="", provider="together", model=self.model,
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
