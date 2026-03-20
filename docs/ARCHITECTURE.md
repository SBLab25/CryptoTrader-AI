# Architecture: Multi-Agent Crypto Trading System

## Goal
A production-grade multi-agent AI system that continuously monitors cryptocurrency markets across exchanges, analyzes price action and signals, and executes trades based on user-defined profit targets and risk parameters — with robust risk management, portfolio tracking, and a real-time dashboard.

---

## Agent Roles (Multi-Agent Orchestration)

```
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR AGENT                     │
│     Coordinates all sub-agents, manages state,          │
│     enforces risk limits, routes decisions               │
└────────┬──────────┬──────────┬──────────┬───────────────┘
         │          │          │          │
    ┌────▼───┐ ┌────▼───┐ ┌───▼────┐ ┌──▼──────┐
    │MARKET  │ │SIGNAL  │ │RISK    │ │EXECUTION│
    │ANALYST │ │AGENT   │ │MANAGER │ │AGENT    │
    │        │ │        │ │        │ │         │
    │- OHLCV │ │- TA    │ │- PnL   │ │- Orders │
    │- Order │ │- Sent. │ │- Limits│ │- Fills  │
    │  book  │ │- AI    │ │- DD    │ │- Slipp. │
    └────────┘ └────────┘ └────────┘ └─────────┘
         │          │          │          │
    ┌────▼──────────▼──────────▼──────────▼───────┐
    │              PORTFOLIO AGENT                  │
    │   Tracks positions, P&L, performance metrics  │
    └───────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Agent | Responsibility |
|-------|---------------|
| **Orchestrator** | Master coordinator; routes data between agents; enforces global state |
| **Market Analyst** | Fetches real-time OHLCV, order book, trades from exchanges |
| **Signal Agent** | Runs TA indicators (RSI, MACD, BB, EMA), AI analysis via Claude |
| **Risk Manager** | Enforces stop-loss, take-profit, max drawdown, position sizing |
| **Execution Agent** | Places, monitors, cancels orders; handles slippage |
| **Portfolio Agent** | Tracks open positions, realized/unrealized PnL, reports |

---

## Data Flow

```
Exchange APIs → Market Analyst
             → Signal Agent (TA + AI analysis)
             → Risk Manager (validates trade size & risk)
             → Execution Agent (places orders)
             → Portfolio Agent (tracks results)
             → Dashboard (real-time UI)
```

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Agent Framework | LangGraph | Stateful multi-agent graphs, conditional routing |
| LLM | Anthropic Claude (claude-sonnet-4-20250514) | Market analysis, signal reasoning |
| Backend | FastAPI + Python 3.12 | Async, typed, performant |
| Exchange API | Crypto.com Exchange MCP + CCXT | Multi-exchange support |
| Task Queue | APScheduler | 24/7 polling without overhead |
| Database | SQLite (dev) / PostgreSQL (prod) | Trade logs, position history |
| Frontend | React + Vite + TailwindCSS | Real-time dashboard |
| WebSocket | FastAPI WebSocket | Live price/signal streaming |
| Testing | pytest + pytest-asyncio | Full test coverage |
| Deployment | Docker Compose | One-command deployment |

---

## Risk Management Rules (Non-Negotiable)

1. **Max position size**: Never risk > X% of portfolio on a single trade (configurable)
2. **Stop-loss**: Every trade MUST have a stop-loss order
3. **Take-profit**: Every trade MUST have a take-profit target
4. **Max drawdown**: System pauses if portfolio drops > N% (configurable)
5. **Paper trading mode**: Default ON — must explicitly enable live trading
6. **Daily loss limit**: Auto-pause if daily loss exceeds limit

---

## Folder Structure

```
crypto-trading-agent/
├── app/
│   ├── main.py                  # FastAPI entrypoint
│   ├── config.py                # Settings via pydantic-settings
│   ├── agents/
│   │   ├── orchestrator.py      # Master coordinator (LangGraph)
│   │   ├── market_analyst.py    # Market data collection
│   │   ├── signal_agent.py      # Technical analysis + AI signals
│   │   ├── risk_manager.py      # Risk validation
│   │   ├── execution_agent.py   # Order execution
│   │   └── portfolio_agent.py   # Portfolio tracking
│   ├── api/
│   │   ├── routes/
│   │   │   ├── trades.py
│   │   │   ├── portfolio.py
│   │   │   └── config.py
│   │   └── websocket.py
│   ├── tools/
│   │   ├── exchange_tools.py    # Exchange API wrappers
│   │   ├── ta_tools.py          # Technical analysis
│   │   └── notification_tools.py
│   ├── models/
│   │   ├── trade.py
│   │   ├── signal.py
│   │   └── portfolio.py
│   ├── strategies/
│   │   ├── base.py
│   │   ├── momentum.py
│   │   ├── mean_reversion.py
│   │   └── ai_driven.py
│   ├── risk/
│   │   └── risk_engine.py
│   └── utils/
│       ├── logger.py
│       └── helpers.py
├── tests/
├── docker/
├── frontend/
├── scripts/
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```
