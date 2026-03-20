# File: tests/unit/test_llm_providers.py
"""
Unit tests for the LLM abstraction layer.
Tests the factory, base class, and each provider using mocks —
no real API calls are made.
"""
import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import AsyncMock, MagicMock, patch
from src.llm.base import BaseLLMProvider, LLMResponse, LLMConfig, LLMProvider


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_response(content="OK", error=None, latency=50.0):
    return LLMResponse(
        content=content,
        provider="test",
        model="test-model",
        input_tokens=10,
        output_tokens=5,
        latency_ms=latency,
        error=error,
    )


class ConcreteProvider(BaseLLMProvider):
    """Minimal concrete implementation for testing the base class."""
    def __init__(self, response: LLMResponse):
        super().__init__("test-model")
        self._response = response

    async def complete(self, prompt: str, config=None) -> LLMResponse:
        self._record(self._response)
        return self._response

    async def health_check(self) -> bool:
        return self._response.success


# ── LLMResponse Tests ─────────────────────────────────────────────────────────

class TestLLMResponse:
    def test_success_true_when_content_and_no_error(self):
        r = make_response(content="some text")
        assert r.success is True

    def test_success_false_when_error(self):
        r = make_response(content="", error="timeout")
        assert r.success is False

    def test_success_false_when_empty_content(self):
        r = make_response(content="")
        assert r.success is False

    def test_fields_accessible(self):
        r = make_response(content="hello", latency=123.4)
        assert r.content == "hello"
        assert r.latency_ms == 123.4
        assert r.provider == "test"
        assert r.model == "test-model"


# ── BaseLLMProvider Stats Tests ───────────────────────────────────────────────

class TestBaseLLMProvider:
    @pytest.mark.asyncio
    async def test_stats_increment_on_call(self):
        p = ConcreteProvider(make_response("OK"))
        await p.complete("prompt")
        await p.complete("prompt")
        assert p.stats["calls"] == 2

    @pytest.mark.asyncio
    async def test_error_count_tracks_failures(self):
        p = ConcreteProvider(make_response("", error="fail"))
        await p.complete("prompt")
        await p.complete("prompt")
        assert p.stats["errors"] == 2
        assert p.stats["error_rate_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_avg_latency_computed(self):
        p = ConcreteProvider(make_response("OK", latency=100.0))
        await p.complete("prompt")
        await p.complete("prompt")
        assert p.stats["avg_latency_ms"] == 100.0

    def test_stats_zero_before_any_call(self):
        p = ConcreteProvider(make_response("OK"))
        s = p.stats
        assert s["calls"] == 0
        assert s["errors"] == 0
        assert s["avg_latency_ms"] == 0


# ── Factory Tests ─────────────────────────────────────────────────────────────

class TestFactory:
    def _mock_settings(self, provider="anthropic", model="", fallback=""):
        settings = MagicMock()
        settings.llm_provider = provider
        settings.llm_model = model
        settings.llm_fallback_providers = fallback
        settings.anthropic_api_key = "test-key"
        settings.openai_api_key = "test-key"
        settings.groq_api_key = "test-key"
        settings.openrouter_api_key = "test-key"
        settings.gemini_api_key = "test-key"
        settings.mistral_api_key = "test-key"
        settings.together_api_key = "test-key"
        settings.ollama_base_url = "http://localhost:11434"
        return settings

    def test_create_anthropic_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("anthropic")):
            p = create_provider("anthropic")
            assert p.provider_name == "anthropic"

    def test_create_openai_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("openai")):
            p = create_provider("openai")
            assert p.provider_name == "openai"

    def test_create_groq_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("groq")):
            p = create_provider("groq")
            assert p.provider_name == "groq"

    def test_create_ollama_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("ollama")):
            p = create_provider("ollama")
            assert p.provider_name == "ollama"

    def test_create_openrouter_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("openrouter")):
            p = create_provider("openrouter")
            assert p.provider_name == "openrouter"

    def test_create_gemini_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("gemini")):
            p = create_provider("gemini")
            assert p.provider_name == "gemini"

    def test_create_mistral_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("mistral")):
            p = create_provider("mistral")
            assert p.provider_name == "mistral"

    def test_create_together_provider(self):
        from src.llm.factory import create_provider
        with patch("src.llm.factory.settings", self._mock_settings("together")):
            p = create_provider("together")
            assert p.provider_name == "together"

    def test_unknown_provider_raises(self):
        from src.llm.factory import create_provider
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_provider("nonexistent_llm")

    def test_missing_api_key_raises(self):
        from src.llm.factory import create_provider
        bad_settings = self._mock_settings("openai")
        bad_settings.openai_api_key = ""
        with patch("src.llm.factory.settings", bad_settings):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                create_provider("openai")

    def test_ollama_no_key_required(self):
        from src.llm.factory import create_provider
        settings = self._mock_settings("ollama")
        # Ollama has no API key — should not raise even with empty keys
        with patch("src.llm.factory.settings", settings):
            p = create_provider("ollama")
            assert p is not None

    def test_reset_clears_singleton(self):
        from src.llm import factory
        factory._provider_instance = MagicMock()  # Set something
        factory.reset_llm()
        assert factory._provider_instance is None

    @pytest.mark.asyncio
    async def test_fallback_chain_uses_second_on_failure(self):
        from src.llm.factory import FallbackLLMProvider

        failing = ConcreteProvider(make_response("", error="primary failed"))
        working = ConcreteProvider(make_response("success"))

        chain = FallbackLLMProvider([failing, working])
        result = await chain.complete("test prompt")

        assert result.success is True
        assert result.content == "success"

    @pytest.mark.asyncio
    async def test_fallback_chain_returns_error_when_all_fail(self):
        from src.llm.factory import FallbackLLMProvider

        p1 = ConcreteProvider(make_response("", error="fail1"))
        p2 = ConcreteProvider(make_response("", error="fail2"))

        chain = FallbackLLMProvider([p1, p2])
        result = await chain.complete("test")

        assert result.success is False
        assert "All providers failed" in result.error

    @pytest.mark.asyncio
    async def test_fallback_health_check_returns_true_if_any_healthy(self):
        from src.llm.factory import FallbackLLMProvider

        sick = ConcreteProvider(make_response("", error="down"))
        healthy = ConcreteProvider(make_response("OK"))

        chain = FallbackLLMProvider([sick, healthy])
        assert await chain.health_check() is True


# ── Signal Agent Prompt Parser Tests ─────────────────────────────────────────

class TestSignalAgentParser:
    """Test the JSON parsing logic in the signal agent (no LLM calls)."""

    def _parse(self, raw: str):
        from src.agents.signal_agent import _parse_response
        return _parse_response(raw, fallback_price=50000.0)

    def test_clean_json_parsed(self):
        raw = '{"signal":"buy","confidence":0.8,"reasoning":"good","key_factors":[],"suggested_entry":50000,"suggested_stop_loss":49000,"suggested_take_profit":52000,"risk_warning":null}'
        result = self._parse(raw)
        assert result["signal"] == "buy"
        assert result["confidence"] == 0.8

    def test_markdown_fences_stripped(self):
        raw = '```json\n{"signal":"sell","confidence":0.7,"reasoning":"bearish","key_factors":[],"suggested_entry":50000,"suggested_stop_loss":51000,"suggested_take_profit":48000,"risk_warning":null}\n```'
        result = self._parse(raw)
        assert result["signal"] == "sell"

    def test_leading_text_stripped(self):
        raw = 'Here is my analysis:\n{"signal":"neutral","confidence":0.3,"reasoning":"unclear","key_factors":[],"suggested_entry":50000,"suggested_stop_loss":49000,"suggested_take_profit":52000,"risk_warning":null}'
        result = self._parse(raw)
        assert result["signal"] == "neutral"

    def test_fallback_on_invalid_json(self):
        raw = "This is not JSON at all"
        result = self._parse(raw)
        assert result["signal"] == "neutral"
        assert result["confidence"] == 0.0
        assert result["suggested_entry"] == 50000.0

    def test_fallback_on_empty_string(self):
        result = self._parse("")
        assert result["signal"] == "neutral"

    def test_uppercase_json_fence_stripped(self):
        raw = '```JSON\n{"signal":"strong_buy","confidence":0.9,"reasoning":"strong","key_factors":["RSI oversold"],"suggested_entry":100,"suggested_stop_loss":98,"suggested_take_profit":105,"risk_warning":null}\n```'
        result = self._parse(raw)
        assert result["signal"] == "strong_buy"
        assert result["confidence"] == 0.9


# ── Provider Enum Tests ───────────────────────────────────────────────────────

class TestLLMProviderEnum:
    def test_all_providers_have_string_values(self):
        for p in LLMProvider:
            assert isinstance(p.value, str)
            assert len(p.value) > 0

    def test_provider_names_are_lowercase(self):
        for p in LLMProvider:
            assert p.value == p.value.lower()

    def test_expected_providers_exist(self):
        values = {p.value for p in LLMProvider}
        for expected in ["anthropic", "openai", "groq", "ollama", "openrouter",
                         "gemini", "mistral", "together"]:
            assert expected in values, f"Missing provider: {expected}"


# ── LLMConfig Tests ───────────────────────────────────────────────────────────

class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.max_tokens == 1000
        assert cfg.temperature == 0.1
        assert cfg.system_prompt is None
        assert cfg.timeout_sec == 30

    def test_custom_values(self):
        cfg = LLMConfig(max_tokens=500, temperature=0.5, system_prompt="You are a trader.")
        assert cfg.max_tokens == 500
        assert cfg.temperature == 0.5
        assert cfg.system_prompt == "You are a trader."
