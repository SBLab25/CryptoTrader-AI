# File: src/llm/base.py
"""
LLM Base Provider
Defines the abstract interface that every LLM provider must implement.
All providers return the same structured dict so the signal agent
doesn't care which backend is actually running.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class LLMProvider(str, Enum):
    """All supported LLM backends"""
    ANTHROPIC   = "anthropic"     # Claude (Haiku / Sonnet / Opus)
    OPENAI      = "openai"        # GPT-4o, GPT-4-turbo, GPT-3.5-turbo
    GROQ        = "groq"          # Llama-3, Mixtral, Gemma via Groq Cloud
    OLLAMA      = "ollama"        # Any model running locally via Ollama
    OPENROUTER  = "openrouter"    # 200+ models via OpenRouter API
    GEMINI      = "gemini"        # Google Gemini Pro / Flash
    MISTRAL     = "mistral"       # Mistral AI (mistral-large, mistral-medium)
    TOGETHER    = "together"      # Together AI (open-source models)
    COHERE      = "cohere"        # Cohere Command R+


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider"""
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)


@dataclass
class LLMConfig:
    """Per-request LLM configuration"""
    max_tokens: int = 1000
    temperature: float = 0.1       # Low temperature = deterministic trading signals
    system_prompt: Optional[str] = None
    timeout_sec: int = 30


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Every concrete provider must implement `complete()` and `health_check()`.
    The signal agent calls `complete()` with a plain-text prompt and gets
    back an LLMResponse. Parsing the JSON inside the response is the
    caller's responsibility (done in signal_agent.py).
    """

    def __init__(self, model: str, config: Optional[LLMConfig] = None):
        self.model = model
        self.config = config or LLMConfig()
        self._call_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    @abstractmethod
    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        """
        Send a prompt to the LLM and return the response.

        Args:
            prompt: The user prompt (market data + indicators formatted as text)
            config: Optional per-request overrides for temperature, max_tokens, etc.

        Returns:
            LLMResponse with .content (the raw text) and metadata
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verify the provider is reachable and the API key works.
        Returns True if healthy, False otherwise.
        """
        ...

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Provider", "").lower()

    @property
    def stats(self) -> dict:
        avg_latency = (
            self._total_latency_ms / self._call_count
            if self._call_count else 0
        )
        return {
            "provider": self.provider_name,
            "model": self.model,
            "calls": self._call_count,
            "errors": self._error_count,
            "error_rate_pct": round(self._error_count / self._call_count * 100, 1) if self._call_count else 0,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def _record(self, response: LLMResponse) -> None:
        """Update internal stats after each call"""
        self._call_count += 1
        self._total_latency_ms += response.latency_ms
        if not response.success:
            self._error_count += 1
