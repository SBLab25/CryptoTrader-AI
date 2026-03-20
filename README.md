<div align="center">

# 🤖 CryptoTrader AI

### Multi-Agent Autonomous Crypto Trading System

**Powered by Claude AI (Anthropic) · FastAPI · Real-time WebSocket Dashboard**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Anthropic](https://img.shields.io/badge/Claude_AI-Anthropic-D97706?style=for-the-badge)](https://anthropic.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](docker/)

<br/>

> A production-grade, multi-agent AI system that continuously scans cryptocurrency markets,
> generates intelligent trading signals by combining **technical analysis + Claude AI reasoning**,
> enforces strict risk management, and executes trades — all with a real-time web dashboard.

<br/>

![Dashboard Preview](docs/assets/dashboard-preview.png)

</div>

---

## ✨ Features

| Category | What's Included |
|----------|----------------|
| 🧠 **AI Signals** | Claude AI interprets RSI, MACD, Bollinger Bands, EMA, ATR and generates structured buy/sell decisions with confidence scores |
| 🤖 **Multi-Agent** | 5 specialized agents: Market Analyst, Signal Agent, Risk Manager, Execution Agent, Portfolio Agent — all coordinated by an Orchestrator |
| 📊 **3 Strategies** | Momentum (EMA crossover), Mean Reversion (BB + RSI), Breakout (range + volume) — auto-selects the best per cycle |
| 🛡️ **Risk Engine** | 8-layer validation: R:R ratio, position sizing, stop-loss enforcement, daily loss cap, drawdown halt |
| 📄 **Paper Trading** | Default ON — full simulation with real prices before risking any capital |
| 🔄 **Backtesting** | Replay historical OHLCV through all strategies, compare results, Sharpe ratio, max drawdown, profit factor |
| 📡 **Live Dashboard** | 6-tab real-time SPA: equity chart, positions, signal feed, backtest runner, risk config, activity log |
| 🔔 **Telegram Alerts** | Trade opened/closed, strong signals, risk pause events, daily summary |
| 💾 **Persistence** | SQLAlchemy async ORM (SQLite dev / PostgreSQL prod), Alembic migrations, full trade history API |
| 🌐 **Multi-Exchange** | Crypto.com built-in + CCXT adapter for 100+ exchanges (Binance, Coinbase, Bybit, OKX…) |
| 🐳 **Docker Ready** | One-command deploy with `docker-compose up` |

---

## ⚠️ Important Disclaimer

**No trading system can guarantee profits or zero losses.** Cryptocurrency markets are inherently unpredictable. This system:

- ✅ Uses proven technical analysis combined with AI reasoning
- ✅ Enforces strict risk management on every trade
- ✅ Defaults to **Paper Trading** — safe simulation before real money
- ❌ Cannot predict the future
- ❌ Does not constitute financial advice

**Always paper trade first. Only invest what you can afford to lose entirely.**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       ORCHESTRATOR                               │
│          Runs every 30s · Coordinates all agents                 │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────┐
  │MARKET  │ │SIGNAL  │ │ RISK   │ │EXECUTE │ │  PORTFOLIO   │
  │ANALYST │ │AGENT   │ │ENGINE  │ │ AGENT  │ │    AGENT     │
  │        │ │        │ │        │ │        │ │              │
  │Real-   │ │TA +    │ │8-layer │ │Retry + │ │PnL · Win     │
  │time    │ │Claude  │ │validat.│ │Slip.   │ │Rate · Stats  │
  │OHLCV   │ │AI      │ │+ Sizing│ │Control │ │              │
  └────────┘ └────────┘ └────────┘ └────────┘ └──────────────┘
       │                                              │
  ┌────▼──────────────────────────────────────────────▼────────┐
  │              PAPER TRADING ENGINE (default ON)              │
  │         Real prices · Simulated orders · Zero risk          │
  └─────────────────────────┬───────────────────────────────────┘
                             │  WebSocket
  ┌──────────────────────────▼──────────────────────────────────┐
  │               REAL-TIME DASHBOARD (dashboard/index.html)    │
  │   Signals · Equity Chart · Positions · Backtest · Log       │
  └─────────────────────────────────────────────────────────────┘
```

### The Trading Cycle

```
Every 30 seconds:
1. Fetch real-time OHLCV + ticker from Crypto.com Exchange
2. Compute RSI · MACD · Bollinger Bands · EMA · ATR for each symbol
3. Ask Claude AI to interpret indicators → structured signal + confidence
4. Run 8-layer risk validation (R:R, position size, drawdown check…)
5. Execute approved trades via paper engine (or live exchange)
6. Update portfolio · broadcast to dashboard via WebSocket
7. Persist everything to database
```

---

## 📁 Project Structure

```
cryptotrader-ai/
│
├── src/                          # All application source code
│   ├── agents/                   # The five AI agents
│   │   ├── orchestrator.py       # Master coordinator — runs the trading loop
│   │   ├── market_analyst.py     # Fetches OHLCV + ticker from exchange
│   │   ├── signal_agent.py       # TA indicators + Claude AI → TradeSignal
│   │   ├── execution_agent.py    # Order placement with retry + slippage control
│   │   └── portfolio_agent.py    # Tracks positions, PnL, win rate
│   │
│   ├── api/                      # FastAPI route handlers
│   │   ├── backtest_routes.py    # POST /api/backtest, compare strategies
│   │   └── routes/
│   │       └── history.py        # Trade history + analytics endpoints
│   │
│   ├── backtesting/
│   │   └── engine.py             # Replay OHLCV → Sharpe, drawdown, profit factor
│   │
│   ├── core/                     # App foundation
│   │   ├── config.py             # Pydantic settings from .env
│   │   ├── models.py             # Pydantic models: Trade, Signal, Portfolio, etc.
│   │   └── server.py             # FastAPI app + WebSocket + lifespan
│   │
│   ├── db/
│   │   └── database.py           # SQLAlchemy async ORM, sessions, repositories
│   │
│   ├── exchange/                 # Exchange integrations
│   │   ├── paper_engine.py       # Paper trading simulation engine
│   │   ├── ccxt_adapter.py       # CCXT adapter for 100+ exchanges
│   │   └── indicators.py         # RSI, MACD, BB, EMA, ATR — pure Python
│   │
│   ├── notifications/
│   │   └── telegram.py           # Telegram bot alerts (optional)
│   │
│   ├── risk/
│   │   └── engine.py             # 8-layer risk validation + position sizing
│   │
│   ├── strategies/
│   │   └── strategies.py         # Momentum · Mean Reversion · Breakout
│   │
│   └── utils/
│       ├── logger.py             # Structured logging
│       └── scheduler.py          # Daily tasks: reset, summaries, stale alerts
│
├── dashboard/
│   └── index.html                # Full 6-tab real-time trading dashboard
│
├── tests/
│   ├── unit/                     # 6 unit test modules (35+ tests)
│   │   ├── test_indicators.py    # RSI, MACD, BB, EMA, ATR
│   │   ├── test_risk_engine.py   # All 8 risk rules
│   │   ├── test_portfolio_agent.py
│   │   ├── test_paper_engine.py  # SL/TP simulation
│   │   ├── test_backtest_engine.py
│   │   └── test_execution_agent.py
│   └── integration/
│       └── test_pipeline.py      # End-to-end strategy → risk → portfolio
│
├── migrations/                   # Alembic DB migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial.py        # Creates all 4 tables
│
├── docs/
│   ├── ARCHITECTURE.md           # Full architecture documentation
│   └── guides/
│       ├── DEPLOYMENT.md         # Local, Docker, VPS, systemd
│       └── LIVE_TRADING.md       # Exchange setup, API keys, safety guide
│
├── scripts/
│   ├── start.sh                  # One-command local startup
│   └── cli.py                    # CLI: status, positions, backtest, start/stop
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml        # Backend + Frontend + Redis
│
├── .env.example                  # All configuration options documented
├── .gitignore
├── alembic.ini
├── Makefile                      # make test · make run · make docker-up
├── pyproject.toml                # Modern Python packaging
└── requirements.txt
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com)
- A [Crypto.com Exchange](https://exchange.crypto.com) account *(for live data)*

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/cryptotrader-ai.git
cd cryptotrader-ai
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
ANTHROPIC_API_KEY=sk-ant-...      # Required for AI signals
TRADING_MODE=paper                 # Start safe — never skip this
CRYPTOCOM_SANDBOX=true             # Use testnet first
```

### 3. Install & Run

```bash
# Option A — Script (recommended for first run)
bash scripts/start.sh

# Option B — Manual
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn src.core.server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Open Dashboard

```bash
open dashboard/index.html
# or serve it: python3 -m http.server 3000 --directory dashboard
```

📖 API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Docker (24/7 operation)

```bash
cd docker && docker-compose up --build -d
# Backend:  http://localhost:8000
# Frontend: http://localhost:3000
```

---

## ⚙️ Configuration

All config lives in `.env`. Key settings:

```env
# ── AI ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Exchange ───────────────────────────────────────────────────
CRYPTOCOM_API_KEY=your_key
CRYPTOCOM_API_SECRET=your_secret
CRYPTOCOM_SANDBOX=true          # true = testnet, false = live

# ── Mode ───────────────────────────────────────────────────────
TRADING_MODE=paper              # paper | live

# ── Symbols ────────────────────────────────────────────────────
SYMBOLS=BTC_USDT,ETH_USDT,SOL_USDT,BNB_USDT,XRP_USDT
SCAN_INTERVAL_SECONDS=30

# ── Risk Management ────────────────────────────────────────────
MAX_POSITION_SIZE_PCT=5.0       # Max % of portfolio per trade
STOP_LOSS_PCT=2.0               # Default stop-loss
TAKE_PROFIT_PCT=4.0             # Default take-profit
MAX_DAILY_LOSS_PCT=5.0          # Auto-pause threshold
MAX_DRAWDOWN_PCT=15.0           # Auto-pause threshold
MAX_OPEN_POSITIONS=5

# ── Capital ────────────────────────────────────────────────────
INITIAL_CAPITAL=10000           # Starting capital (paper mode)

# ── Notifications (optional) ───────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 🤖 Multi-LLM Support

The signal agent works with **any** of these LLM providers — just set `LLM_PROVIDER` in your `.env`:

| Provider | `LLM_PROVIDER=` | Default Model | Free Tier | Local |
|----------|-----------------|---------------|-----------|-------|
| **Anthropic Claude** | `anthropic` | `claude-sonnet-4-5-20251022` | ❌ | ❌ |
| **OpenAI GPT** | `openai` | `gpt-4o-mini` | ❌ | ❌ |
| **Groq Cloud** | `groq` | `llama-3.3-70b-versatile` | ✅ | ❌ |
| **Ollama (local)** | `ollama` | `llama3.2` | ✅ | ✅ |
| **OpenRouter** | `openrouter` | `meta-llama/llama-3.3-70b-instruct` | ✅ | ❌ |
| **Google Gemini** | `gemini` | `gemini-2.0-flash` | ✅ | ❌ |
| **Mistral AI** | `mistral` | `mistral-large-latest` | ❌ | ❌ |
| **Together AI** | `together` | `Meta-Llama-3.1-70B-Instruct-Turbo` | ✅ | ❌ |

### Quick switch examples

```env
# Use Groq (fastest, free tier)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_key

# Use Ollama locally (100% free, no internet needed)
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434

# Use Gemini Flash (free tier, very fast)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key

# Use OpenRouter (200+ models, some free)
LLM_PROVIDER=openrouter
LLM_MODEL=meta-llama/llama-3.3-70b-instruct
OPENROUTER_API_KEY=your_key
```

### Fallback chain

If the primary provider fails, the system automatically tries the next one:

```env
LLM_PROVIDER=anthropic
LLM_FALLBACK_PROVIDERS=groq,ollama
```

### Hot-swap without restart

Switch the provider at runtime via the API — no server restart needed:

```bash
curl -X POST "http://localhost:8000/api/llm/switch?provider=groq&model=llama-3.3-70b-versatile"
```

### LLM API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/llm/status` | Current provider, model, call stats |
| `GET /api/llm/health` | Live health check against the provider |
| `GET /api/llm/providers` | All supported providers with model lists |
| `POST /api/llm/switch` | Hot-swap provider without restarting |

### Required packages per provider

```bash
# Anthropic (default — already in requirements.txt)
pip install anthropic

# OpenAI
pip install openai

# Groq
pip install groq

# Ollama, Gemini, Mistral, OpenRouter, Together
# No extra package needed — all use aiohttp REST calls
# Just install Ollama app for local: https://ollama.com
```

---



| Strategy | Best For | Entry Signal |
|----------|----------|-------------|
| **Momentum** | Trending markets | EMA20 crosses EMA50 + MACD histogram positive + RSI 45–65 |
| **Mean Reversion** | Ranging markets | RSI < 30 near lower Bollinger Band (oversold bounce) |
| **Breakout** | Post-consolidation | Price breaks 20-period high/low with volume surge |
| **Auto-Select** | All conditions | Runs all 3, picks highest-confidence signal |

### Technical Indicators

| Indicator | Period | Interpretation |
|-----------|--------|---------------|
| RSI | 14 | < 30 oversold · > 70 overbought |
| MACD | 12/26/9 | Histogram positive = bullish momentum |
| Bollinger Bands | 20, 2σ | %B < 0.2 = buy zone · > 0.8 = sell zone |
| EMA | 20, 50, 200 | Crossover determines trend direction |
| ATR | 14 | Dynamic stop-loss sizing |
| Volume | 20-bar SMA | 1.5× average = confirms breakout |

---

## 🛡️ Risk Management

Every trade passes through **8 sequential checks** before execution:

```
1. System not paused ............. Trading must not be halted
2. Max positions check ........... Respect MAX_OPEN_POSITIONS
3. Signal confidence ≥ 55% ....... Claude must be confident enough
4. Available balance ≥ $10 ....... Minimum viable position size
5. Risk/Reward ratio ≥ 1.5 ....... Reward must outweigh risk
6. Valid stop-loss + take-profit .. Both levels must be set and logical
7. Daily loss limit .............. Auto-pause if daily loss > threshold
8. Drawdown limit ................ Auto-pause if portfolio drops too far
```

Position size is always capped at `MAX_POSITION_SIZE_PCT` of portfolio value.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/api/status` | System status, cycle count, mode |
| `GET` | `/api/portfolio` | Live portfolio snapshot |
| `GET` | `/api/positions` | Open positions list |
| `GET` | `/api/performance` | Win rate, profit factor, stats |
| `GET` | `/api/risk` | Risk engine config + pause status |
| `POST` | `/api/risk/resume` | Resume paused trading |
| `POST` | `/api/trading/start` | Start trading loop |
| `POST` | `/api/trading/stop` | Stop trading loop |
| `GET` | `/api/trades` | Trade history (filterable) |
| `GET` | `/api/trades/{id}` | Single trade detail |
| `GET` | `/api/portfolio/history` | Historical snapshots for charting |
| `GET` | `/api/analytics/pnl-by-symbol` | PnL breakdown per coin |
| `GET` | `/api/analytics/win-loss-by-hour` | Performance by UTC hour |
| `GET` | `/api/analytics/equity-drawdown` | Equity + drawdown series |
| `POST` | `/api/backtest` | Run a strategy backtest |
| `POST` | `/api/backtest/compare` | Compare all 4 strategies |
| `WS` | `/ws` | Real-time feed (signals, trades, portfolio) |

Full interactive docs: **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 🧪 Testing

```bash
# Run all tests
make test

# Unit tests only (no network needed)
make test-unit

# Integration tests
pytest tests/integration/ -v

# With coverage report
make test-cov
open htmlcov/index.html

# Run a specific test
pytest tests/unit/test_risk_engine.py -v -k "test_reject_poor_risk_reward"
```

**Test coverage:**

| Module | Tests | Status |
|--------|-------|--------|
| `src/exchange/indicators.py` | 15 | ✅ |
| `src/risk/engine.py` | 11 | ✅ |
| `src/agents/portfolio_agent.py` | 10 | ✅ |
| `src/exchange/paper_engine.py` | 8 | ✅ |
| `src/backtesting/engine.py` | 12 | ✅ |
| `src/agents/execution_agent.py` | 8 | ✅ |
| Integration pipeline | 18 | ✅ |

---

## 🔑 Exchange API Key Setup

The bot connects to your **exchange account via API keys** — it never touches a private wallet or seed phrase. Your funds stay on the exchange at all times.

### Crypto.com Exchange

1. Log in → **Settings → API Management → Create API Key**
2. Enable: ✅ **Trade** — Disable: ❌ **Withdraw** (critical for safety)
3. Whitelist your server IP
4. Copy key + secret to `.env`

### Adding More Exchanges (CCXT)

```bash
pip install ccxt
```

```python
# src/exchange/ccxt_adapter.py is already built
adapter = CCXTAdapter("binance", api_key="...", api_secret="...", sandbox=True)
await adapter.connect()
```

Supported: Binance, Coinbase, Bybit, OKX, KuCoin, Kraken, and [100+ more](https://docs.ccxt.com/#/?id=exchanges).

---

## 🗓️ Backtesting

Test any strategy against historical-style data before going live:

```bash
# Via CLI
python scripts/cli.py backtest --strategy momentum --trend up --capital 10000

# Via API
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC_USDT","strategy":"best","initial_capital":10000}'

# Compare all strategies
curl -X POST http://localhost:8000/api/backtest/compare
```

**Backtest metrics returned:**

- Total return %
- Win rate
- Profit factor (gross profit / gross loss)
- Max drawdown %
- Sharpe ratio (annualised)
- Average win / average loss
- Equity curve (for charting)

---

## 🚦 Going Live

> ⚠️ **Do not skip paper trading.** Run the system for at least 2 weeks in paper mode and verify:

| Metric | Minimum Threshold |
|--------|------------------|
| Win Rate | ≥ 50% |
| Profit Factor | ≥ 1.3 |
| Max Drawdown | ≤ 10% |
| Total Trades | ≥ 30 (statistical significance) |

When ready:

```env
TRADING_MODE=live
CRYPTOCOM_SANDBOX=false
INITIAL_CAPITAL=500          # Start very small
MAX_POSITION_SIZE_PCT=2.0    # Use conservative sizing
```

Full guide: [`docs/guides/LIVE_TRADING.md`](docs/guides/LIVE_TRADING.md)

---

## 🛠️ Make Commands

```bash
make install        # Install dependencies
make run            # Start the backend server
make run-reload     # Start with hot-reload (dev)
make test           # Run all tests
make test-unit      # Unit tests only
make test-cov       # Tests + HTML coverage report
make lint           # Ruff linter
make format         # Ruff formatter
make db-init        # Apply Alembic migrations
make docker-up      # Start with Docker Compose
make docker-down    # Stop Docker services
make docker-logs    # Tail backend logs
make clean          # Remove cache / build artifacts
```

---

## 📋 CLI Tool

```bash
# System status
python scripts/cli.py status

# View open positions
python scripts/cli.py positions

# Performance stats
python scripts/cli.py performance

# Run a backtest
python scripts/cli.py backtest --strategy momentum --trend up

# Start / stop trading
python scripts/cli.py start
python scripts/cli.py stop

# Resume risk engine
python scripts/cli.py resume
```

---

## 🗺️ Roadmap

- [ ] **PostgreSQL** production persistence (swap from SQLite)
- [ ] **Live CCXT execution** (currently paper-only, adapter is built)
- [ ] **Sentiment analysis** — news + social signals via Claude
- [ ] **Grid trading strategy** — buy/sell grid for sideways markets
- [ ] **DCA (Dollar Cost Averaging)** mode
- [ ] **Portfolio rebalancing** — target allocation enforcement
- [ ] **Web-based config editor** — change risk params from dashboard
- [ ] **Kubernetes manifests** — horizontal scaling
- [ ] **Export trade history** — CSV download for tax reporting
- [ ] **Multi-timeframe analysis** — 1m, 5m, 15m, 1h confluence signals

---

## 🤝 Contributing

Contributions are welcome. Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Write tests for new functionality
4. Run `make test` and `make lint` before submitting
5. Open a pull request with a clear description

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

## ⚡ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| AI / LLM | Anthropic Claude · OpenAI · Groq · Ollama · OpenRouter · Gemini · Mistral · Together |
| Backend | FastAPI + Uvicorn |
| Real-time | WebSocket (native FastAPI) |
| Database | SQLAlchemy async + SQLite / PostgreSQL |
| Migrations | Alembic |
| Exchange | Crypto.com REST API + CCXT |
| Notifications | Telegram Bot API |
| Testing | pytest + pytest-asyncio |
| Packaging | pyproject.toml + pip |
| Deploy | Docker + Docker Compose |
| Linting | Ruff |

---

<div align="center">


*Trade responsibly. This is not financial advice.*

</div>
