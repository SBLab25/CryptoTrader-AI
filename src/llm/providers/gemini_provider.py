# File: src/llm/providers/gemini_provider.py
"""
Google Gemini Provider
Supports: gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash, gemini-1.0-pro
"""
import time
from typing import Optional

import aiohttp

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini via REST API.
    Requires: Google AI Studio API key (free tier available).
    Get key: https://aistudio.google.com/app/apikey
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, config: Optional[LLMConfig] = None):
        super().__init__(model, config)
        self._api_key = api_key

    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        cfg = config or self.config
        start = time.monotonic()

        parts = [{"text": prompt}]
        contents = [{"role": "user", "parts": parts}]

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": cfg.max_tokens,
                "temperature": cfg.temperature,
            },
        }

        if cfg.system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": cfg.system_prompt}]
            }

        url = f"{BASE_URL}/{self.model}:generateContent?key={self._api_key}"

        try:
            timeout = aiohttp.ClientTimeout(total=cfg.timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Gemini HTTP {resp.status}: {body[:300]}")
                    data = await resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini returned no candidates")

            content = candidates[0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="gemini",
                model=self.model,
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[Gemini] Error ({self.model}): {e}")
            result = LLMResponse(
                content="", provider="gemini", model=self.model,
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
