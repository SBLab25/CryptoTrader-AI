# File: src/llm/providers/openrouter_provider.py
"""
OpenRouter Provider
Access 200+ models from one API key:
  - Meta Llama 3.3 70B, 405B
  - Mistral Large, Mixtral 8x22B
  - Google Gemini Pro, Flash
  - Anthropic Claude (via OpenRouter)
  - DeepSeek V3, R1
  - Qwen 2.5 72B
  - Microsoft Phi-4
  - Cohere Command R+
  - ...and hundreds more

Model names use the format: "provider/model-name"
e.g. "meta-llama/llama-3.3-70b-instruct", "mistralai/mistral-large"
See full list: https://openrouter.ai/models
"""
import time
from typing import Optional

import aiohttp

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter via its OpenAI-compatible REST API.
    Gives access to 200+ models with a single API key.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        site_url: str = "https://github.com/cryptotrader-ai",
        site_name: str = "CryptoTrader AI",
        config: Optional[LLMConfig] = None,
    ):
        super().__init__(model, config)
        self._api_key = api_key
        self._site_url = site_url
        self._site_name = site_name

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._site_url,
            "X-Title": self._site_name,
        }

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

        try:
            timeout = aiohttp.ClientTimeout(total=cfg.timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"OpenRouter HTTP {resp.status}: {body[:300]}")
                    data = await resp.json()

            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="openrouter",
                model=self.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[OpenRouter] Error ({self.model}): {e}")
            result = LLMResponse(
                content="", provider="openrouter", model=self.model,
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
