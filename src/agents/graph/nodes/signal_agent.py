"""Phase 3 signal node."""

from __future__ import annotations

import time
from datetime import datetime

from src.agents.signal_agent import generate_signal
from src.core.models import MarketData


def _select_strategy(indicators: dict) -> str:
    rsi = indicators.get("rsi")
    bb_percent_b = indicators.get("bb_percent_b")
    volume_ratio = indicators.get("volume_ratio") or 1.0
    ema_trend = indicators.get("ema_trend")
    macd_histogram = indicators.get("macd_histogram") or 0.0

    if rsi is not None and bb_percent_b is not None and (
        (rsi <= 30 and bb_percent_b <= 0.2) or (rsi >= 70 and bb_percent_b >= 0.8)
    ):
        return "mean_reversion"
    if volume_ratio >= 1.8:
        return "breakout"
    if ema_trend in {"bullish", "bearish"} and abs(macd_histogram) > 0.01:
        return "momentum"
    return "momentum"


def _build_market_data(state: dict) -> MarketData:
    tick = state["tick"]
    ohlcv = state.get("ohlcv") or []
    return MarketData(
        symbol=state["symbol"],
        price=float(tick["close"]),
        bid=float(tick["close"]),
        ask=float(tick["close"]),
        volume_24h=float(tick.get("volume", 0.0)),
        change_24h_pct=0.0,
        high_24h=max(float(c["high"]) for c in ohlcv[-96:]) if ohlcv else float(tick["high"]),
        low_24h=min(float(c["low"]) for c in ohlcv[-96:]) if ohlcv else float(tick["low"]),
        timestamp=datetime.utcnow(),
        ohlcv=ohlcv,
    )


async def signal_agent_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        market_data = _build_market_data(state)
        strategy = _select_strategy(state.get("indicators") or {})
        rag_hits = []
        try:
            from src.memory.retriever import retrieve_similar_signals

            rag_hits = await retrieve_similar_signals(state.get("indicators") or {}, state["symbol"], strategy=strategy)
        except Exception:
            rag_hits = []
        signal = await generate_signal(state["symbol"], market_data, state.get("ohlcv") or [])
        if signal is None:
            return {
                "signal": {"action": "HOLD", "confidence": 0.0, "strategy": strategy},
                "selected_strategy": strategy,
                "errors": [],
                "node_timings": {"signal_agent": round((time.monotonic() - started) * 1000, 2), "rag_hits": len(rag_hits)},
            }

        signal_dict = {
            "id": signal.id,
            "symbol": signal.symbol,
            "action": signal.signal.value.upper(),
            "confidence": signal.confidence,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "entry_price": signal.entry_price,
            "strategy": strategy,
            "reasoning": signal.reasoning,
            "ai_analysis": signal.ai_analysis,
            "indicators": signal.indicators,
        }
        return {
            "signal": signal_dict,
            "selected_strategy": strategy,
            "errors": [],
            "node_timings": {"signal_agent": round((time.monotonic() - started) * 1000, 2), "rag_hits": len(rag_hits)},
        }
    except Exception as exc:
        return {
            "signal": {"action": "HOLD", "confidence": 0.0},
            "errors": [f"signal_agent_node failed: {exc}"],
            "node_timings": {"signal_agent": round((time.monotonic() - started) * 1000, 2)},
        }
