# Live Trading Integration Guide

## Step-by-Step: Activating Live Trading

This guide walks you through safely transitioning from paper trading to live trading.

---

## Phase 1 — Paper Trading Validation (Minimum 2 Weeks)

Before risking real capital, validate the system behaves correctly:

### Metrics to Hit Before Going Live

| Metric | Minimum Threshold | Why |
|--------|------------------|-----|
| Win Rate | ≥ 50% | Minimum for profitability at 1.5 R:R |
| Profit Factor | ≥ 1.3 | Gross profit / gross loss ratio |
| Max Drawdown | ≤ 10% | Risk tolerance benchmark |
| Consecutive Losses | ≤ 5 | Streak risk check |
| Total Trades | ≥ 30 | Statistical significance |

Check these via:
```bash
curl http://localhost:8000/api/performance
python scripts/cli.py performance
```

---

## Phase 2 — Exchange API Setup

### Crypto.com Exchange

1. Log in to [Crypto.com Exchange](https://exchange.crypto.com)
2. Go to **Settings → API Management → Create API Key**
3. Set permissions:
   - ✅ Trade (required)
   - ❌ Withdraw (NEVER enable)
   - ❌ Transfer (not needed)
4. Add your server IP to the whitelist
5. Copy the API Key and Secret to `.env`

```bash
CRYPTOCOM_API_KEY=your_api_key_here
CRYPTOCOM_API_SECRET=your_api_secret_here
CRYPTOCOM_SANDBOX=false    # Switch from testnet to mainnet
```

### Binance (via CCXT)

```bash
pip install ccxt

BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=false
```

### Other Exchanges

Any of the 100+ CCXT-supported exchanges work the same way. See [ccxt docs](https://docs.ccxt.com) for exchange-specific setup.

---

## Phase 3 — Enable Live Execution

Update `app/tools/exchange_tools.py` to wire in the live client.

Replace the `MockExchangeClient` reference in `orchestrator.py`:

```python
# In app/agents/orchestrator.py, replace:
self.exchange_client = MockExchangeClient(self.paper_engine)

# With (for Crypto.com):
from app.tools.exchange_tools import CryptocomExchangeClient

self.exchange_client = CryptocomExchangeClient(
    api_key=settings.cryptocom_api_key,
    api_secret=settings.cryptocom_api_secret,
    sandbox=settings.cryptocom_sandbox,
)
```

Update `ExecutionAgent._place_live_order` in `app/agents/execution_agent.py`:

```python
async def _place_live_order(self, symbol, side, quantity, price):
    # Example: Crypto.com market order
    return await self.exchange_client.place_order(
        instrument_name=symbol,
        side=side,
        order_type="MARKET",
        quantity=quantity,
    )
```

---

## Phase 4 — Risk Configuration for Live Trading

Tighten risk parameters before first live trade:

```bash
# .env — conservative live settings
TRADING_MODE=live
MAX_POSITION_SIZE_PCT=2.0      # Start smaller than paper
STOP_LOSS_PCT=1.5              # Tighter stops
TAKE_PROFIT_PCT=3.0            # 2:1 R:R minimum
MAX_DAILY_LOSS_PCT=3.0         # Lower daily limit
MAX_DRAWDOWN_PCT=8.0           # Tighter drawdown guard
MAX_OPEN_POSITIONS=3           # Fewer concurrent positions
INITIAL_CAPITAL=500            # Start very small
```

---

## Phase 5 — First Live Trade Checklist

Before the first live trade fires:

- [ ] Paper trading metrics pass Phase 1 thresholds
- [ ] API keys are on mainnet and tested with a manual small order
- [ ] `CRYPTOCOM_SANDBOX=false` confirmed
- [ ] `TRADING_MODE=live` confirmed
- [ ] Telegram notifications are working (test with a `/api/risk/resume` call)
- [ ] Dashboard is open and WebSocket is connected
- [ ] You are available to monitor the first 2 hours

---

## Emergency Stop Procedures

### Immediate: Via API
```bash
curl -X POST http://localhost:8000/api/trading/stop
```

### Via CLI
```bash
python scripts/cli.py stop
```

### Via Dashboard
Click **⏹ Stop** in the dashboard Controls panel.

### Nuclear: Kill the process
```bash
# Docker
docker-compose stop backend

# Systemd
sudo systemctl stop crypto-trader

# Local
Ctrl+C in the terminal running uvicorn
```

---

## Monitoring Live Trades

### Real-time dashboard
Open `frontend/dashboard.html` → Positions tab

### Telegram alerts
You'll receive notifications for:
- Every trade opened/closed
- Strong signals (≥80% confidence)
- Risk engine pauses
- Daily summaries at midnight UTC

### API polling
```bash
watch -n 5 'curl -s http://localhost:8000/api/portfolio | python3 -m json.tool'
```

---

## Capital Scaling Strategy

| Stage | Capital | Duration | Condition to Advance |
|-------|---------|----------|---------------------|
| Paper | $0 (virtual $10,000) | 2+ weeks | Win rate ≥50%, PF ≥1.3 |
| Micro live | $100–500 | 2+ weeks | Consistent with paper results |
| Small live | $500–2,000 | 1+ month | Drawdown ≤ paper drawdown |
| Medium live | $2,000–10,000 | 3+ months | Sharpe ≥ 1.0 |
| Full deployment | $10,000+ | Ongoing | All metrics stable |

Never skip stages. Each validates that the system performs as expected at that scale.

---

## Legal & Tax Considerations

- ⚠️ Crypto trading profits are taxable in most jurisdictions
- Keep records of all trades (available via `GET /api/trades`)
- The trade history API provides CSV-exportable data for tax reporting
- Consult a tax professional familiar with crypto in your jurisdiction

---

## Disclaimer

This system is provided for educational and research purposes. It is not financial advice. Trading cryptocurrency carries substantial risk of loss. Past performance (including backtests) does not guarantee future results. Only trade with capital you can afford to lose entirely.
