# Production Deployment Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required |
| Docker | 24+ | For containerised deployment |
| Docker Compose | 2.x | For multi-service deployment |
| Crypto.com Exchange Account | — | For live trading |
| Anthropic API Key | — | For AI signal generation |

---

## Deployment Options

### Option A: Local / VPS (Recommended for personal use)

#### 1. Clone & Configure

```bash
git clone https://github.com/yourname/crypto-trading-agent
cd crypto-trading-agent
cp .env.example .env
```

Edit `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
CRYPTOCOM_API_KEY=your_key
CRYPTOCOM_API_SECRET=your_secret
CRYPTOCOM_SANDBOX=true         # Start on testnet!
TRADING_MODE=paper             # Start in paper mode!
```

#### 2. Install & Run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head            # Apply DB migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 3. Open Dashboard

```
http://localhost:8000/docs      # Swagger API docs
open frontend/dashboard.html    # Full dashboard
```

---

### Option B: Docker Compose (Recommended for 24/7 operation)

```bash
cp .env.example .env
# Edit .env with your API keys
cd docker
docker-compose up --build -d
```

Services started:
- `backend` — Trading engine on port 8000
- `frontend` — Dashboard on port 3000
- `redis` — Cache / rate limiting on port 6379

View logs:
```bash
docker-compose logs -f backend
```

Stop:
```bash
docker-compose down
```

---

### Option C: Systemd Service (for VPS auto-start)

Create `/etc/systemd/system/crypto-trader.service`:

```ini
[Unit]
Description=Crypto Trading Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/crypto-trading-agent
EnvironmentFile=/home/trader/crypto-trading-agent/.env
ExecStart=/home/trader/crypto-trading-agent/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable crypto-trader
sudo systemctl start crypto-trader
sudo journalctl -u crypto-trader -f    # View logs
```

---

## Database Setup

### SQLite (Development — default)
No setup needed. Database is created automatically at `trading.db`.

### PostgreSQL (Production — recommended for multi-instance)

```bash
# Install asyncpg driver
pip install asyncpg

# Update .env
DATABASE_URL=postgresql://trader:yourpassword@localhost:5432/trading

# Apply migrations
alembic upgrade head
```

---

## Security Checklist

Before going live, verify:

- [ ] `.env` is in `.gitignore` — never commit API keys
- [ ] `CRYPTOCOM_SANDBOX=false` only after thorough paper testing
- [ ] `TRADING_MODE=live` only after validating on testnet
- [ ] API keys have **minimum required permissions** (trade only, no withdrawal)
- [ ] Firewall: port 8000 is not exposed publicly (use reverse proxy)
- [ ] `SECRET_KEY` is set to a strong random value
- [ ] `MAX_POSITION_SIZE_PCT` is set conservatively (≤5%)
- [ ] `MAX_DAILY_LOSS_PCT` is set (≤5% recommended)
- [ ] Telegram notifications configured for trade alerts

---

## Enabling Live Trading

⚠️ **Do this only after running paper trading for ≥2 weeks with consistent results.**

1. Validate your Crypto.com API keys work on sandbox
2. Set `CRYPTOCOM_SANDBOX=false`
3. Set `TRADING_MODE=live`
4. Update `app/tools/exchange_tools.py`:
   - Replace `MockExchangeClient` with `CryptocomExchangeClient`
   - Wire `CryptocomExchangeClient` into `ExecutionAgent._place_live_order`
5. Start with **small capital** (≤$500)
6. Monitor the first 24h closely

---

## Adding More Exchanges (via CCXT)

```bash
pip install ccxt
```

In `.env`:
```bash
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
```

In `app/agents/market_analyst.py`, add:
```python
from app.tools.ccxt_adapter import CCXTAdapter

binance = CCXTAdapter("binance", api_key=..., api_secret=..., sandbox=True)
await binance.connect()
```

---

## Monitoring & Observability

### API Health Check
```bash
curl http://localhost:8000/
curl http://localhost:8000/api/status
curl http://localhost:8000/api/portfolio
```

### CLI Tool
```bash
python scripts/cli.py status
python scripts/cli.py positions
python scripts/cli.py performance
python scripts/cli.py backtest --strategy momentum --trend up
```

### Logs
```bash
# Docker
docker-compose logs -f backend

# Systemd
journalctl -u crypto-trader -f

# Local
uvicorn app.main:app --log-level info
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (no network required)
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=app --cov-report=html
open htmlcov/index.html

# Specific test file
pytest tests/unit/test_ta_tools.py -v -k "test_rsi"
```

---

## Database Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after changing models
alembic revision --autogenerate -m "add_new_column"

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

---

## Performance Tuning

| Setting | Conservative | Moderate | Aggressive |
|---------|-------------|----------|------------|
| `MAX_POSITION_SIZE_PCT` | 2% | 5% | 10% |
| `STOP_LOSS_PCT` | 1.5% | 2% | 3% |
| `TAKE_PROFIT_PCT` | 3% | 4% | 6% |
| `MAX_DAILY_LOSS_PCT` | 3% | 5% | 8% |
| `MAX_OPEN_POSITIONS` | 3 | 5 | 8 |
| `SCAN_INTERVAL_SECONDS` | 60 | 30 | 15 |

Start conservative. Expand after validating profitability.

---

## Troubleshooting

**"No market data available"**
→ Check internet connectivity and Crypto.com API status

**"Signal confidence too low"**
→ Market conditions are unclear. This is correct behaviour — the system is protecting capital.

**"Trading PAUSED: Daily loss limit exceeded"**
→ Call `POST /api/risk/resume` or wait until midnight (UTC) for auto-reset.

**"Insufficient balance for minimum trade size"**
→ Either increase capital or reduce `MAX_OPEN_POSITIONS`.

**WebSocket keeps disconnecting**
→ Check that the backend is running and `WS_URL` in the dashboard matches.

**"ModuleNotFoundError: ccxt"**
→ Run `pip install ccxt` to enable multi-exchange support.
