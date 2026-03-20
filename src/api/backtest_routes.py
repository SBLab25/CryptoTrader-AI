# File: src/api/backtest_routes.py
"""
Additional API routes: backtest, trade history, portfolio history
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import math

from src.backtesting.engine import BacktestEngine, compare_strategies
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Backtest & History"])


# ── Request / Response Models ─────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str = "BTC_USDT"
    strategy: str = "momentum"       # momentum | mean_reversion | breakout | best
    timeframe: str = "15m"
    initial_capital: float = 10000.0
    position_size_pct: float = 5.0
    min_confidence: float = 0.55


class MockOHLCVRequest(BaseModel):
    """For testing backtest without live data"""
    n_candles: int = 200
    trend: str = "up"           # up | down | ranging | volatile
    start_price: float = 50000.0


# ── Mock OHLCV Generator ──────────────────────────────────────────────────────

def _generate_mock_ohlcv(n: int, trend: str, start: float) -> list:
    import math, random
    random.seed(42)
    data = []
    price = start

    for i in range(n):
        if trend == "up":
            change = random.uniform(-0.008, 0.018)
        elif trend == "down":
            change = random.uniform(-0.018, 0.008)
        elif trend == "ranging":
            change = 0.008 * math.sin(i * 0.25) + random.uniform(-0.004, 0.004)
        else:  # volatile
            change = random.uniform(-0.03, 0.03)

        price = max(price * (1 + change), 0.01)
        o = price * (1 + random.uniform(-0.003, 0.003))
        h = price * (1 + abs(random.uniform(0, 0.01)))
        l = price * (1 - abs(random.uniform(0, 0.01)))
        vol = random.uniform(800, 5000)
        data.append({
            "timestamp": i * 900000,
            "open": o, "high": h, "low": l, "close": price, "volume": vol,
        })
    return data


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/backtest")
async def run_backtest(req: BacktestRequest, mock: Optional[MockOHLCVRequest] = None):
    """
    Run a backtest using mock OHLCV data (or provide your own data).

    In production, replace mock OHLCV with historical data from the exchange.
    """
    try:
        # Use mock data (replace with real historical data fetch in production)
        if mock:
            ohlcv = _generate_mock_ohlcv(mock.n_candles, mock.trend, mock.start_price)
        else:
            ohlcv = _generate_mock_ohlcv(300, "up", 50000)

        engine = BacktestEngine(
            initial_capital=req.initial_capital,
            position_size_pct=req.position_size_pct / 100,
            min_confidence=req.min_confidence,
        )
        result = engine.run(
            ohlcv,
            strategy=req.strategy,
            symbol=req.symbol,
            timeframe=req.timeframe,
        )

        summary = result.summary()
        # Add equity curve (sampled for large datasets)
        curve = result.equity_curve
        if len(curve) > 200:
            step = len(curve) // 200
            curve = curve[::step]
        summary["equity_curve"] = [round(v, 2) for v in curve]

        return summary

    except Exception as e:
        logger.error(f"[BACKTEST API] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest/compare")
async def compare_all_strategies(
    mock: Optional[MockOHLCVRequest] = None,
    initial_capital: float = 10000.0,
):
    """Compare all strategies side by side on the same dataset"""
    try:
        if mock:
            ohlcv = _generate_mock_ohlcv(mock.n_candles, mock.trend, mock.start_price)
        else:
            ohlcv = _generate_mock_ohlcv(300, "up", 50000)

        results = compare_strategies(ohlcv, initial_capital=initial_capital)
        return {
            strategy: result.summary()
            for strategy, result in results.items()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtest/strategies")
async def list_strategies():
    """List available trading strategies with descriptions"""
    return {
        "strategies": [
            {
                "id": "momentum",
                "name": "Momentum (EMA Crossover + MACD)",
                "description": "Rides strong trends using EMA20/EMA50 crossover and MACD confirmation. Best in trending markets.",
                "best_for": "trending",
            },
            {
                "id": "mean_reversion",
                "name": "Mean Reversion (Bollinger + RSI)",
                "description": "Buys oversold bounces and sells overbought extremes using Bollinger Bands and RSI. Best in ranging markets.",
                "best_for": "ranging",
            },
            {
                "id": "breakout",
                "name": "Breakout (Range Break + Volume)",
                "description": "Detects price breaking out of consolidation ranges with volume confirmation. Best after low-volatility periods.",
                "best_for": "breakout",
            },
            {
                "id": "best",
                "name": "Auto-Select Best Strategy",
                "description": "Runs all strategies and picks the one with the highest confidence signal per cycle.",
                "best_for": "all",
            },
        ]
    }
