# File: tests/conftest.py
"""
Pytest configuration and shared fixtures.

This file is loaded by pytest BEFORE any test modules are imported.
It sets all required environment variables so pydantic-settings can
initialise src.core.config.settings without a real .env file.

This is the standard approach for testing pydantic-settings apps in CI.
"""
import os
import pytest

# ── Set all required env vars before any src.* imports ───────────────────────
# These are placeholder values — no real API calls are made in unit tests.
_TEST_ENV = {
    # LLM
    "LLM_PROVIDER":            "anthropic",
    "LLM_MODEL":               "",
    "LLM_FALLBACK_PROVIDERS":  "",
    "ANTHROPIC_API_KEY":       "test-key-ci-anthropic",
    "OPENAI_API_KEY":          "test-key-ci-openai",
    "GROQ_API_KEY":            "test-key-ci-groq",
    "OPENROUTER_API_KEY":      "test-key-ci-openrouter",
    "GEMINI_API_KEY":          "test-key-ci-gemini",
    "MISTRAL_API_KEY":         "test-key-ci-mistral",
    "TOGETHER_API_KEY":        "test-key-ci-together",
    "OLLAMA_BASE_URL":         "http://localhost:11434",
    # Exchange
    "CRYPTOCOM_API_KEY":       "",
    "CRYPTOCOM_API_SECRET":    "",
    "CRYPTOCOM_SANDBOX":       "true",
    "BINANCE_API_KEY":         "",
    "BINANCE_API_SECRET":      "",
    "BINANCE_TESTNET":         "true",
    # Trading
    "TRADING_MODE":            "paper",
    "SYMBOLS":                 "BTC_USDT,ETH_USDT",
    "SCAN_INTERVAL_SECONDS":   "30",
    "BASE_CURRENCY":           "USDT",
    "INITIAL_CAPITAL":         "10000",
    # Risk
    "MAX_POSITION_SIZE_PCT":   "5.0",
    "STOP_LOSS_PCT":           "2.0",
    "TAKE_PROFIT_PCT":         "4.0",
    "MAX_DAILY_LOSS_PCT":      "5.0",
    "MAX_DRAWDOWN_PCT":        "15.0",
    "MAX_OPEN_POSITIONS":      "5",
    # DB / API / Misc
    "DATABASE_URL":            "sqlite:///./test_ci.db",
    "API_HOST":                "0.0.0.0",
    "API_PORT":                "8000",
    "SECRET_KEY":              "ci-test-secret-key",
    "LOG_LEVEL":               "WARNING",
    "TELEGRAM_BOT_TOKEN":      "",
    "TELEGRAM_CHAT_ID":        "",
}

for key, val in _TEST_ENV.items():
    os.environ.setdefault(key, val)


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_ohlcv():
    """Generate a reusable OHLCV dataset for strategy/backtest tests."""
    import math
    import random
    random.seed(42)
    data, price = [], 100.0
    for i in range(150):
        change = random.uniform(-0.006, 0.015)
        price = max(price * (1 + change), 0.01)
        data.append({
            "timestamp": i * 900_000,
            "open":   price * 0.999,
            "high":   price * 1.005,
            "low":    price * 0.994,
            "close":  price,
            "volume": random.uniform(500, 5000),
        })
    return data


@pytest.fixture(scope="session")
def test_prices(test_ohlcv):
    """Close price series extracted from test_ohlcv."""
    return [c["close"] for c in test_ohlcv]
