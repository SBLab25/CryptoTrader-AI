# File: src/llm/providers/ollama_provider.py
"""
Ollama Provider — Local LLM inference
Runs any model locally: llama3.2, mistral, qwen2.5, phi3, deepseek-r1,
gemma2, codellama, and hundreds more from ollama.com/library.

Requirements:
  1. Install Ollama: https://ollama.com
  2. Pull a model:   ollama pull llama3.2
  3. Ollama server runs automatically at http://localhost:11434

No API key required — completely free and private.
"""
import time
import json
from typing import Optional

import aiohttp

from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(BaseLLMProvider):
    """
    Ollama local inference via its REST API.
    No SDK needed — uses aiohttp directly.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        config: Optional[LLMConfig] = None,
    ):
        super().__init__(model, config)
        self._base_url = base_url.rstrip("/")

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
            "stream": False,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
            },
        }

        try:
            timeout = aiohttp.ClientTimeout(total=cfg.timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:200]}")
                    data = await resp.json()

            content = data.get("message", {}).get("content", "")
            latency = (time.monotonic() - start) * 1000

            result = LLMResponse(
                content=content,
                provider="ollama",
                model=self.model,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                latency_ms=round(latency, 1),
            )

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"[Ollama] Error ({self.model}): {e}")
            result = LLMResponse(
                content="", provider="ollama", model=self.model,
                latency_ms=round(latency, 1), error=str(e),
            )

        self._record(result)
        return result

    async def health_check(self) -> bool:
        """Check if Ollama server is running and the model is available"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Check server is up
                async with session.get(f"{self._base_url}/api/tags") as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.json()

            # Check requested model is pulled
            available = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
            model_base = self.model.split(":")[0]
            if model_base not in available:
                logger.warning(
                    f"[Ollama] Model '{self.model}' not found. "
                    f"Run: ollama pull {self.model}\n"
                    f"Available: {available}"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"[Ollama] Health check failed: {e}. Is Ollama running?")
            return False

    async def list_models(self) -> list:
        """Return list of locally available model names"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self._base_url}/api/tags") as resp:
                    data = await resp.json()
                    return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return []
