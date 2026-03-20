# File: src/core/config.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os


class Settings(BaseSettings):
    # ── LLM Provider Selection ────────────────────────────────────────────────
    # Which provider to use: anthropic | openai | groq | ollama |
    #                        openrouter | gemini | mistral | together
    llm_provider: str = Field(default="anthropic", env="LLM_PROVIDER")

    # Override the default model for the chosen provider (optional)
    # Leave blank to use each provider's recommended default model
    llm_model: str = Field(default="", env="LLM_MODEL")

    # Comma-separated fallback providers if the primary fails
    # e.g. "groq,ollama" — tried in order after primary fails
    llm_fallback_providers: str = Field(default="", env="LLM_FALLBACK_PROVIDERS")

    # ── LLM API Keys ──────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    groq_api_key: str = Field(default="", env="GROQ_API_KEY")
    openrouter_api_key: str = Field(default="", env="OPENROUTER_API_KEY")
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    mistral_api_key: str = Field(default="", env="MISTRAL_API_KEY")
    together_api_key: str = Field(default="", env="TOGETHER_API_KEY")

    # ── Ollama (local models, no API key needed) ──────────────────────────────
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")

    # ── Exchange API Keys ─────────────────────────────────────────────────────
    # Exchange credentials
    cryptocom_api_key: str = Field(default="", env="CRYPTOCOM_API_KEY")
    cryptocom_api_secret: str = Field(default="", env="CRYPTOCOM_API_SECRET")
    cryptocom_sandbox: bool = Field(default=True, env="CRYPTOCOM_SANDBOX")

    binance_api_key: str = Field(default="", env="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", env="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=True, env="BINANCE_TESTNET")

    # Trading mode
    trading_mode: str = Field(default="paper", env="TRADING_MODE")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Risk management
    max_position_size_pct: float = Field(default=5.0, env="MAX_POSITION_SIZE_PCT")
    stop_loss_pct: float = Field(default=2.0, env="STOP_LOSS_PCT")
    take_profit_pct: float = Field(default=4.0, env="TAKE_PROFIT_PCT")
    max_daily_loss_pct: float = Field(default=5.0, env="MAX_DAILY_LOSS_PCT")
    max_drawdown_pct: float = Field(default=15.0, env="MAX_DRAWDOWN_PCT")
    max_open_positions: int = Field(default=5, env="MAX_OPEN_POSITIONS")

    # Portfolio
    initial_capital: float = Field(default=10000.0, env="INITIAL_CAPITAL")
    base_currency: str = Field(default="USDT", env="BASE_CURRENCY")

    # Scanning
    scan_interval_seconds: int = Field(default=30, env="SCAN_INTERVAL_SECONDS")
    symbols: str = Field(
        default="BTC_USDT,ETH_USDT,SOL_USDT,BNB_USDT,XRP_USDT",
        env="SYMBOLS"
    )

    # Database
    database_url: str = Field(default="sqlite:///./trading.db", env="DATABASE_URL")

    # API
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    secret_key: str = Field(default="dev-secret-key", env="SECRET_KEY")

    # Notifications
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", env="TELEGRAM_CHAT_ID")

    @property
    def symbol_list(self) -> List[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def is_live_trading(self) -> bool:
        return self.trading_mode.lower() == "live"

    @property
    def active_llm_key(self) -> str:
        """Return the API key for the currently selected provider"""
        key_map = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
            "gemini": self.gemini_api_key,
            "mistral": self.mistral_api_key,
            "together": self.together_api_key,
            "ollama": "no-key-needed",
        }
        return key_map.get(self.llm_provider.lower(), "")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
