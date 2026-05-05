# File: src/agents/signal_agent.py
"""
Signal Agent
Combines technical analysis with any LLM provider for intelligent signal generation.

Phase 2 adds signal logging and LLM latency capture while keeping the
existing signal generation workflow intact.
"""

import asyncio
import json
import time
from typing import List, Optional

from src.core.config import settings
from src.core.models import MarketData, SignalStrength, TradeSignal
from src.db.database import get_db_session
from src.db.timescale import SignalLogStore
from src.exchange.indicators import analyze_indicators
from src.llm.base import LLMConfig
from src.llm.factory import get_llm
from src.risk.engine import risk_engine
from src.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert cryptocurrency trading analyst with deep knowledge of "
    "technical analysis, market microstructure, and risk management. "
    "Always respond with valid JSON only - no preamble, no markdown, no text outside JSON."
)


def build_analysis_prompt(symbol: str, indicators: dict, market_data: MarketData) -> str:
    return f"""Analyse the following market data and technical indicators for {symbol}.

## Market Data
- Current Price:  ${market_data.price:,.4f}
- 24h Change:     {market_data.change_24h_pct:+.2f}%
- 24h Volume:     ${market_data.volume_24h:,.0f}
- 24h High/Low:   ${market_data.high_24h:,.4f} / ${market_data.low_24h:,.4f}
- Bid / Ask:      ${market_data.bid:,.4f} / ${market_data.ask:,.4f}

## Technical Indicators
- RSI (14):        {indicators.get('rsi', 'N/A')}
- MACD:            {indicators.get('macd', {})}
- Bollinger Bands: {indicators.get('bollinger_bands', {})}
- EMA 20 / 50:     {indicators.get('ema_20', 'N/A')} / {indicators.get('ema_50', 'N/A')}
- ATR:             {indicators.get('atr', 'N/A')}
- Trend:           {indicators.get('trend', 'N/A')}
- Volume vs Avg:   {indicators.get('volume_vs_avg', 'N/A')}x
- Technical Bias:  {indicators.get('technical_bias', 'N/A')} ({indicators.get('signal_strength', 0):.0%})

Respond ONLY with a JSON object (no markdown fences):
{{
  "signal": "strong_buy"|"buy"|"neutral"|"sell"|"strong_sell",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<2-3 sentences>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "suggested_entry": <float>,
  "suggested_stop_loss": <float>,
  "suggested_take_profit": <float>,
  "risk_warning": "<string or null>"
}}

Rules:
- Stop-loss BELOW entry for buys, ABOVE for sells
- Take-profit ABOVE entry for buys, BELOW for sells
- Minimum 1.5:1 risk/reward ratio
- Use neutral + low confidence if the setup is unclear"""


def _parse_response(raw: str, fallback_price: float) -> dict:
    text = raw.strip()
    if "```" in text:
        fenced = text[text.find("```") + 3:]
        first_newline = fenced.find("\n")
        if first_newline != -1:
            language = fenced[:first_newline].strip()
            if language and "{" not in language:
                fenced = fenced[first_newline + 1 :]
        fence_end = fenced.find("```")
        text = fenced[:fence_end] if fence_end != -1 else fenced
        text = text.strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[SIGNAL] Could not parse LLM JSON - using neutral fallback")
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "reasoning": "LLM parse error",
            "key_factors": [],
            "suggested_entry": fallback_price,
            "suggested_stop_loss": fallback_price * 0.98,
            "suggested_take_profit": fallback_price * 1.04,
            "risk_warning": "Parse error",
        }


async def analyze_with_llm(symbol: str, indicators: dict, market_data: MarketData) -> tuple[dict, dict]:
    prompt = build_analysis_prompt(symbol, indicators, market_data)
    llm = get_llm()
    cfg = LLMConfig(max_tokens=1000, temperature=0.1, system_prompt=SYSTEM_PROMPT, timeout_sec=30)

    logger.debug(f"[SIGNAL] Calling {llm.provider_name}/{llm.model} for {symbol}")
    response = await llm.complete(prompt, cfg)

    meta = {"provider": llm.provider_name, "model": llm.model, "latency_ms": response.latency_ms}
    if not response.success:
        logger.error(f"[SIGNAL] {llm.provider_name} failed for {symbol}: {response.error}")
        return (
            {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"LLM unavailable: {response.error}",
                "key_factors": [],
                "suggested_entry": market_data.price,
                "suggested_stop_loss": market_data.price * 0.98,
                "suggested_take_profit": market_data.price * 1.04,
                "risk_warning": f"Provider {llm.provider_name} failed",
            },
            meta,
        )

    logger.debug(f"[SIGNAL] {llm.provider_name}/{llm.model} -> {response.latency_ms:.0f}ms")
    return _parse_response(response.content, market_data.price), meta


async def _persist_signal_log(signal: TradeSignal, indicators: dict, llm_meta: dict, latency_ms: int) -> None:
    try:
        async with get_db_session() as session:
            await SignalLogStore.insert(
                session,
                {
                    "id": signal.id,
                    "symbol": signal.symbol,
                    "strategy": "ai_llm_ta",
                    "action": signal.signal.value,
                    "confidence": signal.confidence,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "entry_price": signal.entry_price,
                    "rsi": indicators.get("rsi"),
                    "macd_histogram": (indicators.get("macd") or {}).get("histogram"),
                    "bb_percent_b": (indicators.get("bollinger_bands") or {}).get("percent_b"),
                    "ema_trend": indicators.get("trend"),
                    "atr": indicators.get("atr"),
                    "reasoning": signal.reasoning,
                    "llm_provider": llm_meta.get("provider"),
                    "llm_model": llm_meta.get("model"),
                    "llm_latency_ms": latency_ms,
                    "risk_passed": None,
                    "mode": settings.trading_mode,
                },
            )
    except Exception as exc:
        logger.warning(f"[SIGNAL] signal log write failed for {signal.symbol}: {exc}")


async def generate_signal(symbol: str, market_data: MarketData, ohlcv: List[dict]) -> Optional[TradeSignal]:
    if len(ohlcv) < 30:
        return None

    indicators = analyze_indicators(ohlcv)
    if "error" in indicators:
        return None

    started = time.monotonic()
    ai_result, llm_meta = await analyze_with_llm(symbol, indicators, market_data)
    latency_ms = int((time.monotonic() - started) * 1000)

    signal_map = {
        "strong_buy": SignalStrength.STRONG_BUY,
        "buy": SignalStrength.BUY,
        "neutral": SignalStrength.NEUTRAL,
        "sell": SignalStrength.SELL,
        "strong_sell": SignalStrength.STRONG_SELL,
    }
    signal_str = ai_result.get("signal", "neutral").lower().replace(" ", "_")
    signal_enum = signal_map.get(signal_str, SignalStrength.NEUTRAL)
    confidence = float(ai_result.get("confidence", 0.0))

    entry = float(ai_result.get("suggested_entry", market_data.price))
    atr = indicators.get("atr")
    side = "buy" if signal_enum in [SignalStrength.BUY, SignalStrength.STRONG_BUY] else "sell"

    raw_sl = ai_result.get("suggested_stop_loss")
    raw_tp = ai_result.get("suggested_take_profit")
    stop_loss = float(raw_sl) if raw_sl else risk_engine.compute_stop_loss(entry, side, atr)
    take_profit = float(raw_tp) if raw_tp else risk_engine.compute_take_profit(entry, stop_loss, side)

    if (side == "buy" and (stop_loss >= entry or take_profit <= entry)) or (
        side == "sell" and (stop_loss <= entry or take_profit >= entry)
    ):
        logger.warning(f"[SIGNAL] {symbol}: LLM gave invalid levels - recomputing from ATR")
        stop_loss = risk_engine.compute_stop_loss(entry, side, atr)
        take_profit = risk_engine.compute_take_profit(entry, stop_loss, side)

    trade_signal = TradeSignal(
        symbol=symbol,
        signal=signal_enum,
        confidence=confidence,
        reasoning=ai_result.get("reasoning", ""),
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        indicators=indicators,
        ai_analysis=str(ai_result.get("key_factors", [])),
    )
    await _persist_signal_log(trade_signal, indicators, llm_meta, latency_ms)

    if signal_enum == SignalStrength.NEUTRAL or confidence < 0.50:
        logger.info(f"[SIGNAL] {symbol}: {signal_str} ({confidence:.0%}) - skipping")
        return None

    logger.info(
        f"[SIGNAL] {symbol}: {signal_str.upper()} | {confidence:.0%} | "
        f"{llm_meta.get('provider')}/{llm_meta.get('model')} | "
        f"Entry:{entry:.4f} SL:{stop_loss:.4f} TP:{take_profit:.4f}"
    )
    return trade_signal


async def generate_signals_batch(market_data_map: dict, ohlcv_map: dict) -> List[TradeSignal]:
    results = await asyncio.gather(
        *[generate_signal(sym, md, ohlcv_map.get(sym, [])) for sym, md in market_data_map.items()],
        return_exceptions=True,
    )
    signals = []
    for result in results:
        if isinstance(result, TradeSignal):
            signals.append(result)
        elif isinstance(result, Exception):
            logger.error(f"[SIGNAL] Batch error: {result}")
    return signals
