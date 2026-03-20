# File: src/llm/factory.py
"""
LLM Factory
Reads LLM_PROVIDER + model settings from .env and returns
the appropriate provider instance. Also supports a fallback chain —
if the primary provider fails, automatically tries the next one.
"""
from __future__ import annotations

from typing import Optional, List
from src.llm.base import BaseLLMProvider, LLMProvider, LLMConfig, LLMResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_provider(
    provider_name: str,
    model: Optional[str] = None,
    config: Optional[LLMConfig] = None,
) -> BaseLLMProvider:
    """
    Factory function — returns the correct provider instance based on name.

    Args:
        provider_name: One of the LLMProvider enum values (case-insensitive)
        model: Override the default model for this provider
        config: Optional LLMConfig overrides

    Returns:
        Instantiated and configured BaseLLMProvider

    Raises:
        ValueError: If provider_name is unknown
        RuntimeError: If required API key is missing
    """
    from src.core.config import settings

    name = provider_name.lower().strip()

    if name == LLMProvider.ANTHROPIC:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
        from src.llm.providers.anthropic_provider import AnthropicProvider, DEFAULT_MODEL
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.OPENAI:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        from src.llm.providers.openai_provider import OpenAIProvider, DEFAULT_MODEL
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.GROQ:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        from src.llm.providers.groq_provider import GroqProvider, DEFAULT_MODEL
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.OLLAMA:
        from src.llm.providers.ollama_provider import OllamaProvider, DEFAULT_MODEL
        return OllamaProvider(
            model=model or settings.llm_model or DEFAULT_MODEL,
            base_url=settings.ollama_base_url,
            config=config,
        )

    elif name == LLMProvider.OPENROUTER:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in .env")
        from src.llm.providers.openrouter_provider import OpenRouterProvider, DEFAULT_MODEL
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.GEMINI:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        from src.llm.providers.gemini_provider import GeminiProvider, DEFAULT_MODEL
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.MISTRAL:
        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is not set in .env")
        from src.llm.providers.mistral_provider import MistralProvider, DEFAULT_MODEL
        return MistralProvider(
            api_key=settings.mistral_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    elif name == LLMProvider.TOGETHER:
        if not settings.together_api_key:
            raise RuntimeError("TOGETHER_API_KEY is not set in .env")
        from src.llm.providers.together_provider import TogetherProvider, DEFAULT_MODEL
        return TogetherProvider(
            api_key=settings.together_api_key,
            model=model or settings.llm_model or DEFAULT_MODEL,
            config=config,
        )

    else:
        supported = [p.value for p in LLMProvider]
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported: {supported}"
        )


def get_provider_from_settings() -> BaseLLMProvider:
    """
    Read LLM_PROVIDER from settings and return configured provider.
    This is the main entry point used by the signal agent.
    """
    from src.core.config import settings
    provider_name = settings.llm_provider

    try:
        provider = create_provider(provider_name, config=LLMConfig(
            max_tokens=1000,
            temperature=0.1,
        ))
        logger.info(
            f"[LLM] Using provider: {provider_name.upper()} | "
            f"Model: {provider.model}"
        )
        return provider
    except Exception as e:
        logger.error(f"[LLM] Failed to initialise '{provider_name}': {e}")
        raise


class FallbackLLMProvider(BaseLLMProvider):
    """
    Tries providers in order — falls back to the next one if a call fails.
    Useful for high-availability setups.

    Example config in .env:
        LLM_PROVIDER=anthropic
        LLM_FALLBACK_PROVIDERS=groq,openai,ollama
    """

    def __init__(self, providers: List[BaseLLMProvider]):
        if not providers:
            raise ValueError("FallbackLLMProvider requires at least one provider")
        primary = providers[0]
        super().__init__(primary.model)
        self._providers = providers

    async def complete(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        last_error = None
        for i, provider in enumerate(self._providers):
            if i > 0:
                logger.warning(
                    f"[LLM Fallback] Switching to {provider.provider_name}/{provider.model}"
                )
            response = await provider.complete(prompt, config)
            if response.success:
                self._call_count += 1
                return response
            last_error = response.error

        # All providers failed
        self._call_count += 1
        self._error_count += 1
        return LLMResponse(
            content="", provider="fallback", model="none",
            error=f"All providers failed. Last error: {last_error}",
        )

    async def health_check(self) -> bool:
        for provider in self._providers:
            if await provider.health_check():
                return True
        return False


def get_fallback_chain() -> BaseLLMProvider:
    """
    Build a fallback chain from LLM_PROVIDER + LLM_FALLBACK_PROVIDERS env vars.
    Returns a single FallbackLLMProvider wrapping all configured providers.
    """
    from src.core.config import settings

    providers = []

    # Primary
    try:
        providers.append(create_provider(settings.llm_provider))
    except Exception as e:
        logger.error(f"[LLM] Primary provider failed: {e}")

    # Fallbacks
    if settings.llm_fallback_providers:
        for name in settings.llm_fallback_providers.split(","):
            name = name.strip()
            if not name:
                continue
            try:
                providers.append(create_provider(name))
                logger.info(f"[LLM] Fallback registered: {name}")
            except Exception as e:
                logger.warning(f"[LLM] Fallback '{name}' could not be configured: {e}")

    if not providers:
        raise RuntimeError("No LLM providers could be initialised. Check your .env API keys.")

    if len(providers) == 1:
        return providers[0]

    logger.info(
        f"[LLM] Fallback chain: "
        + " → ".join(f"{p.provider_name}/{p.model}" for p in providers)
    )
    return FallbackLLMProvider(providers)


# ── Cached singleton ──────────────────────────────────────────────────────────
_provider_instance: Optional[BaseLLMProvider] = None


def get_llm() -> BaseLLMProvider:
    """
    Get the global LLM provider instance (singleton).
    Created once on first call, reused for all subsequent calls.
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = get_fallback_chain()
    return _provider_instance


def reset_llm() -> None:
    """Force recreation of the LLM provider (e.g. after config change)"""
    global _provider_instance
    _provider_instance = None
