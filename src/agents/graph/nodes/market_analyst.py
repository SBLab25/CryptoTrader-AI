"""Phase 3 market analyst node."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.agents.graph.runtime import market_analyst
from src.db.database import get_db_session
from src.db.timescale import OHLCVStore
from src.exchange.indicators import analyze_indicators

MIN_CANDLES_REQUIRED = 30


async def _read_from_timescale(symbol: str, limit: int = 200) -> list[dict]:
    async with get_db_session() as session:
        return await OHLCVStore.get_latest(session, symbol=symbol, limit=limit)


async def _fetch_from_exchange(symbol: str, limit: int = 200) -> list[dict]:
    candles = await market_analyst.fetch_ohlcv(symbol, timeframe="15m", limit=limit)
    normalized = []
    for candle in candles:
        ts = candle.get("timestamp")
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).replace(tzinfo=None)
        normalized.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle["volume"]),
                "source": candle.get("source", "rest"),
            }
        )
    return normalized


def _compute_indicators(ohlcv: list[dict]) -> dict:
    indicators = analyze_indicators(ohlcv)
    if "error" in indicators:
        return {}
    macd = indicators.get("macd") or {}
    bollinger = indicators.get("bollinger_bands") or {}
    return {
        "rsi": indicators.get("rsi"),
        "macd_histogram": macd.get("histogram"),
        "bb_percent_b": bollinger.get("percent_b"),
        "ema_trend": indicators.get("trend"),
        "atr": indicators.get("atr"),
        "volume_ratio": indicators.get("volume_vs_avg"),
        "raw": indicators,
    }


async def market_analyst_node(state: dict) -> dict:
    started = time.monotonic()
    symbol = state["symbol"]
    try:
        ohlcv = await _read_from_timescale(symbol)
        if len(ohlcv) < MIN_CANDLES_REQUIRED:
            ohlcv = await _fetch_from_exchange(symbol)
        if len(ohlcv) < MIN_CANDLES_REQUIRED:
            return {
                "ohlcv": ohlcv,
                "indicators": {},
                "errors": [f"Insufficient OHLCV data for {symbol}"],
                "node_timings": {"market_analyst": round((time.monotonic() - started) * 1000, 2)},
            }
        return {
            "ohlcv": ohlcv,
            "indicators": _compute_indicators(ohlcv),
            "errors": [],
            "node_timings": {"market_analyst": round((time.monotonic() - started) * 1000, 2)},
        }
    except Exception as exc:
        return {
            "ohlcv": [],
            "indicators": {},
            "errors": [f"market_analyst_node failed: {exc}"],
            "node_timings": {"market_analyst": round((time.monotonic() - started) * 1000, 2)},
        }
