# File: tests/unit/test_llm_providers.py
"""
Unit tests for the LLM abstraction layer.
No real API calls are made — all providers are tested with mocked responses.
"""
import pytest
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
    """Minimal concrete provider for testing BaseLLMProvider logic."""

    def __init__(self, response: LLMResponse):
        super().__init__("test-model")
        self._response = response

    async def complete(self, prompt: str, config=None) -> LLMResponse:
        self._record(self._response)
        return self._response

    async def health_check(self) -> bool:
        return self._response.success


def make_mock_settings(provider="anthropic", model="", fallback=""):
    """Return a MagicMock that looks like src.core.config.settings."""
    s = MagicMock()
    s.llm_provider = provider
    s.llm_model = model
    s.llm_fallback_providers = fallback
    s.anthropic_api_key   = "test-key"
    s.openai_api_key      = "test-key"
    s.groq_api_key        = "test-key"
    s.openrouter_api_key  = "test-key"
    s.gemini_api_key      = "test-key"
    s.mistral_api_key     = "test-key"
    s.together_api_key    = "test-key"
    s.ollama_base_url     = "http://localhost:11434"
    return s


# ── LLMResponse ───────────────────────────────────────────────────────────────

class TestLLMResponse:
    def test_success_when_content_present(self):
        assert make_response(content="hello").success is True

    def test_failure_when_error_set(self):
        assert make_response(content="", error="timeout").success is False

    def test_failure_when_content_empty(self):
        assert make_response(content="").success is False

    def test_fields_accessible(self):
        r = make_response(content="hello", latency=99.9)
        assert r.content == "hello"
        assert r.latency_ms == 99.9
        assert r.provider == "test"
        assert r.model == "test-model"


# ── BaseLLMProvider ───────────────────────────────────────────────────────────

class TestBaseLLMProvider:
    @pytest.mark.asyncio
    async def test_call_count_increments(self):
        p = ConcreteProvider(make_response("OK"))
        await p.complete("a")
        await p.complete("b")
        assert p.stats["calls"] == 2

    @pytest.mark.asyncio
    async def test_error_count_tracks_failures(self):
        p = ConcreteProvider(make_response("", error="fail"))
        await p.complete("x")
        await p.complete("x")
        assert p.stats["errors"] == 2
        assert p.stats["error_rate_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_avg_latency_computed(self):
        p = ConcreteProvider(make_response("OK", latency=100.0))
        await p.complete("x")
        await p.complete("x")
        assert p.stats["avg_latency_ms"] == 100.0

    def test_zero_stats_before_any_call(self):
        p = ConcreteProvider(make_response("OK"))
        assert p.stats["calls"] == 0
        assert p.stats["errors"] == 0
        assert p.stats["avg_latency_ms"] == 0


# ── LLMProvider Enum ──────────────────────────────────────────────────────────

class TestLLMProviderEnum:
    def test_all_eight_providers_present(self):
        values = {p.value for p in LLMProvider}
        for name in ["anthropic", "openai", "groq", "ollama",
                     "openrouter", "gemini", "mistral", "together"]:
            assert name in values, f"Missing provider: {name}"

    def test_all_values_are_lowercase_strings(self):
        for p in LLMProvider:
            assert isinstance(p.value, str)
            assert p.value == p.value.lower()


# ── LLMConfig ────────────────────────────────────────────────────────────────

class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.max_tokens   == 1000
        assert cfg.temperature  == 0.1
        assert cfg.system_prompt is None
        assert cfg.timeout_sec  == 30

    def test_custom_values(self):
        cfg = LLMConfig(max_tokens=500, temperature=0.7, system_prompt="You are a trader.")
        assert cfg.max_tokens    == 500
        assert cfg.temperature   == 0.7
        assert cfg.system_prompt == "You are a trader."


# ── Factory: provider creation ────────────────────────────────────────────────
# Patch target is src.core.config.settings because factory.py does:
#   from src.core.config import settings  (inside each function)
# That import creates a local reference — we patch the source module.

PATCH_TARGET = "src.core.config.settings"


class TestFactory:
    def test_create_anthropic(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("anthropic")):
            p = create_provider("anthropic")
        assert p.provider_name == "anthropic"

    def test_create_openai(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("openai")):
            p = create_provider("openai")
        assert p.provider_name == "openai"

    def test_create_groq(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("groq")):
            p = create_provider("groq")
        assert p.provider_name == "groq"

    def test_create_ollama(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("ollama")):
            p = create_provider("ollama")
        assert p.provider_name == "ollama"

    def test_create_openrouter(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("openrouter")):
            p = create_provider("openrouter")
        assert p.provider_name == "openrouter"

    def test_create_gemini(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("gemini")):
            p = create_provider("gemini")
        assert p.provider_name == "gemini"

    def test_create_mistral(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("mistral")):
            p = create_provider("mistral")
        assert p.provider_name == "mistral"

    def test_create_together(self):
        from src.llm.factory import create_provider
        with patch(PATCH_TARGET, make_mock_settings("together")):
            p = create_provider("together")
        assert p.provider_name == "together"

    def test_unknown_provider_raises_value_error(self):
        from src.llm.factory import create_provider
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_provider("nonexistent_xyz")

    def test_missing_api_key_raises_runtime_error(self):
        from src.llm.factory import create_provider
        bad = make_mock_settings("openai")
        bad.openai_api_key = ""
        with patch(PATCH_TARGET, bad):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                create_provider("openai")

    def test_ollama_works_without_api_key(self):
        from src.llm.factory import create_provider
        s = make_mock_settings("ollama")
        with patch(PATCH_TARGET, s):
            p = create_provider("ollama")
        assert p is not None

    def test_reset_clears_singleton(self):
        from src.llm import factory
        factory._provider_instance = MagicMock()
        factory.reset_llm()
        assert factory._provider_instance is None


# ── Fallback chain ────────────────────────────────────────────────────────────

class TestFallbackChain:
    @pytest.mark.asyncio
    async def test_falls_back_to_second_provider_on_failure(self):
        from src.llm.factory import FallbackLLMProvider
        failing = ConcreteProvider(make_response("", error="primary down"))
        working = ConcreteProvider(make_response("success"))
        chain   = FallbackLLMProvider([failing, working])

        result = await chain.complete("test prompt")
        assert result.success is True
        assert result.content == "success"

    @pytest.mark.asyncio
    async def test_returns_error_when_all_providers_fail(self):
        from src.llm.factory import FallbackLLMProvider
        p1 = ConcreteProvider(make_response("", error="fail1"))
        p2 = ConcreteProvider(make_response("", error="fail2"))

        result = await FallbackLLMProvider([p1, p2]).complete("test")
        assert result.success is False
        assert "All providers failed" in result.error

    @pytest.mark.asyncio
    async def test_health_check_passes_if_any_provider_healthy(self):
        from src.llm.factory import FallbackLLMProvider
        sick    = ConcreteProvider(make_response("", error="down"))
        healthy = ConcreteProvider(make_response("OK"))

        assert await FallbackLLMProvider([sick, healthy]).health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_fails_when_all_providers_down(self):
        from src.llm.factory import FallbackLLMProvider
        p1 = ConcreteProvider(make_response("", error="down"))
        p2 = ConcreteProvider(make_response("", error="down"))

        assert await FallbackLLMProvider([p1, p2]).health_check() is False


# ── JSON response parser ──────────────────────────────────────────────────────

class TestSignalParser:
    """Test the JSON parsing logic used in signal_agent.py."""

    def _parse(self, raw: str, price: float = 50000.0):
        from src.agents.signal_agent import _parse_response

        return _parse_response(raw, price)

    _GOOD = ('{"signal":"buy","confidence":0.8,"reasoning":"bullish",'
             '"key_factors":[],"suggested_entry":100,'
             '"suggested_stop_loss":98,"suggested_take_profit":104,'
             '"risk_warning":null}')

    def test_parses_clean_json(self):
        r = self._parse(self._GOOD)
        assert r["signal"] == "buy"
        assert r["confidence"] == 0.8

    def test_strips_markdown_fences(self):
        r = self._parse(f"```json\n{self._GOOD}\n```")
        assert r["signal"] == "buy"

    def test_strips_leading_text(self):
        r = self._parse(f"My analysis:\n{self._GOOD}")
        assert r["signal"] == "buy"

    def test_fallback_on_invalid_json(self):
        r = self._parse("This is not JSON", price=12345.0)
        assert r["signal"] == "neutral"
        assert r["confidence"] == 0.0
        assert r["suggested_entry"] == 12345.0

    def test_fallback_on_empty_string(self):
        r = self._parse("", price=99999.0)
        assert r["signal"] == "neutral"

    def test_strong_sell_parsed(self):
        raw = ('{"signal":"strong_sell","confidence":0.9,"reasoning":"bearish",'
               '"key_factors":[],"suggested_entry":200,'
               '"suggested_stop_loss":210,"suggested_take_profit":180,'
               '"risk_warning":null}')
        r = self._parse(raw)
        assert r["signal"] == "strong_sell"
        assert r["confidence"] == 0.9
