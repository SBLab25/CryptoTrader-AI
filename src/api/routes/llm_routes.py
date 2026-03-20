# File: src/api/routes/llm_routes.py
"""
LLM Provider API Routes
Exposes provider status, health checks, and model lists.
"""
from fastapi import APIRouter, HTTPException
from src.llm.factory import get_llm, reset_llm, create_provider
from src.llm.base import LLMProvider
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/llm", tags=["LLM Provider"])


@router.get("/status")
async def llm_status():
    """Get current LLM provider info and call statistics."""
    llm = get_llm()
    return {
        "provider": llm.provider_name,
        "model": llm.model,
        "stats": llm.stats,
        "configured_provider": settings.llm_provider,
        "configured_model": settings.llm_model or "(default)",
        "fallback_providers": settings.llm_fallback_providers or "(none)",
    }


@router.get("/health")
async def llm_health():
    """Run a live health check against the configured LLM provider."""
    llm = get_llm()
    logger.info(f"[LLM API] Health check: {llm.provider_name}/{llm.model}")
    healthy = await llm.health_check()
    return {
        "provider": llm.provider_name,
        "model": llm.model,
        "healthy": healthy,
        "status": "ok" if healthy else "unreachable",
    }


@router.get("/providers")
async def list_providers():
    """List all supported LLM providers with their default models and setup requirements."""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "default_model": "claude-sonnet-4-5-20251022",
                "models": ["claude-opus-4-5", "claude-sonnet-4-5-20251022", "claude-haiku-4-5-20251001"],
                "requires_key": "ANTHROPIC_API_KEY",
                "local": False,
                "free_tier": False,
                "notes": "Best reasoning quality. Recommended default.",
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "default_model": "gpt-4o-mini",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                "requires_key": "OPENAI_API_KEY",
                "local": False,
                "free_tier": False,
                "notes": "Widely used. gpt-4o-mini is cost-effective.",
            },
            {
                "id": "groq",
                "name": "Groq Cloud",
                "default_model": "llama-3.3-70b-versatile",
                "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
                "requires_key": "GROQ_API_KEY",
                "local": False,
                "free_tier": True,
                "notes": "Fastest inference (100-500 tok/s). Great for real-time signals. Free tier available.",
            },
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "default_model": "llama3.2",
                "models": ["llama3.2", "mistral", "qwen2.5", "phi3", "deepseek-r1", "gemma2"],
                "requires_key": None,
                "local": True,
                "free_tier": True,
                "notes": "100% free, private, offline. Install Ollama + pull a model. No API key needed.",
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "default_model": "meta-llama/llama-3.3-70b-instruct",
                "models": ["meta-llama/llama-3.3-70b-instruct", "mistralai/mistral-large", "google/gemini-flash-1.5"],
                "requires_key": "OPENROUTER_API_KEY",
                "local": False,
                "free_tier": True,
                "notes": "200+ models via one API key. Some models are free. Good fallback option.",
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "default_model": "gemini-2.0-flash",
                "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
                "requires_key": "GEMINI_API_KEY",
                "local": False,
                "free_tier": True,
                "notes": "Free tier available via Google AI Studio. Flash model is very fast.",
            },
            {
                "id": "mistral",
                "name": "Mistral AI",
                "default_model": "mistral-large-latest",
                "models": ["mistral-large-latest", "mistral-medium-latest", "open-mixtral-8x22b"],
                "requires_key": "MISTRAL_API_KEY",
                "local": False,
                "free_tier": False,
                "notes": "Strong European alternative. Good multilingual support.",
            },
            {
                "id": "together",
                "name": "Together AI",
                "default_model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"],
                "requires_key": "TOGETHER_API_KEY",
                "local": False,
                "free_tier": True,
                "notes": "Open-source models. Free $25 credit on signup.",
            },
        ],
        "current": settings.llm_provider,
    }


@router.post("/switch")
async def switch_provider(provider: str, model: str = ""):
    """
    Hot-switch the LLM provider without restarting the server.
    Changes take effect on the next trading cycle.
    """
    supported = [p.value for p in LLMProvider]
    if provider.lower() not in supported:
        raise HTTPException(400, f"Unknown provider '{provider}'. Supported: {supported}")

    # Test the new provider before switching
    try:
        test_provider = create_provider(provider, model=model or None)
        healthy = await test_provider.health_check()
        if not healthy:
            raise HTTPException(503, f"Provider '{provider}' health check failed. Check your API key.")
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    # Update settings and reset singleton
    settings.llm_provider = provider.lower()
    if model:
        settings.llm_model = model
    reset_llm()

    logger.info(f"[LLM API] Switched to {provider}/{model or 'default'}")
    return {
        "status": "switched",
        "provider": provider,
        "model": model or "(default)",
        "message": f"LLM provider switched to {provider}. Takes effect on next cycle.",
    }
