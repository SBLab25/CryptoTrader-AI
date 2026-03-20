# File: src/agents/signal_agent.py
"""
Signal Agent
Combines technical analysis with any LLM provider for intelligent signal generation.

Supported providers (set LLM_PROVIDER in .env):
  anthropic  → Claude Sonnet / Opus / Haiku
  openai     → GPT-4o, GPT-4-turbo, GPT-3.5-turbo
  groq       → Llama 3.3, Mixtral, Gemma (ultra-fast)
  ollama     → Any local model (Llama, Mistral, Qwen, Phi, DeepSeek…)
  openrouter → 200+ models via one API key
  gemini     → Google Gemini 2.0 Flash / 1.5 Pro
  mistral    → Mistral Large, Mixtral 8x22B
  together   → Open-source models at scale
"""
import asyncio
import json
from typing import List, Optional

from src.core.models import TradeSignal, SignalStrength, MarketData
from src.exchange.indicators import analyze_indicators
from src.risk.engine import risk_engine
from src.core.config import settings
from src.llm.factory import get_llm
from src.llm.base import LLMConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert cryptocurrency trading analyst with deep knowledge of "
    "technical analysis, market microstructure, and risk management. "
    "Always respond with valid JSON only — no preamble, no markdown, no text outside JSON."
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
    for fence in ["```json", "```JSON", "```"]:
        if fence in text:
            parts = text.split(fence)
            text = parts[1] if len(parts) > 2 else parts[-1]
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[SIGNAL] Could not parse LLM JSON — using neutral fallback")
        return {
            "signal": "neutral", "confidence": 0.0,
            "reasoning": "LLM parse error", "key_factors": [],
            "suggested_entry": fallback_price,
            "suggested_stop_loss": fallback_price * 0.98,
            "suggested_take_profit": fallback_price * 1.04,
            "risk_warning": "Parse error",
        }


async def analyze_with_llm(
    symbol: str,
    indicators: dict,
    market_data: MarketData,
) -> dict:
    prompt = build_analysis_prompt(symbol, indicators, market_data)
    llm = get_llm()
    cfg = LLMConfig(max_tokens=1000, temperature=0.1, system_prompt=SYSTEM_PROMPT, timeout_sec=30)

    logger.debug(f"[SIGNAL] Calling {llm.provider_name}/{llm.model} for {symbol}")
    response = await llm.complete(prompt, cfg)

    if not response.success:
        logger.error(f"[SIGNAL] {llm.provider_name} failed for {symbol}: {response.error}")
        return {
            "signal": "neutral", "confidence": 0.0,
            "reasoning": f"LLM unavailable: {response.error}", "key_factors": [],
            "suggested_entry": market_data.price,
            "suggested_stop_loss": market_data.price * 0.98,
            "suggested_take_profit": market_data.price * 1.04,
            "risk_warning": f"Provider {llm.provider_name} failed",
        }

    logger.debug(f"[SIGNAL] {llm.provider_name}/{llm.model} → {response.latency_ms:.0f}ms")
    return _parse_response(response.content, market_data.price)


async def generate_signal(
    symbol: str,
    market_data: MarketData,
    ohlcv: List[dict],
) -> Optional[TradeSignal]:
    if len(ohlcv) < 30:
        return None

    indicators = analyze_indicators(ohlcv)
    if "error" in indicators:
        return None

    ai_result = await analyze_with_llm(symbol, indicators, market_data)

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

    if signal_enum == SignalStrength.NEUTRAL or confidence < 0.50:
        logger.info(f"[SIGNAL] {symbol}: {signal_str} ({confidence:.0%}) — skipping")
        return None

    entry = float(ai_result.get("suggested_entry", market_data.price))
    atr = indicators.get("atr")
    side = "buy" if signal_enum in [SignalStrength.BUY, SignalStrength.STRONG_BUY] else "sell"

    raw_sl = ai_result.get("suggested_stop_loss")
    raw_tp = ai_result.get("suggested_take_profit")
    stop_loss = float(raw_sl) if raw_sl else risk_engine.compute_stop_loss(entry, side, atr)
    take_profit = float(raw_tp) if raw_tp else risk_engine.compute_take_profit(entry, stop_loss, side)

    # Sanity-check levels
    if (side == "buy" and (stop_loss >= entry or take_profit <= entry)) or \
       (side == "sell" and (stop_loss <= entry or take_profit >= entry)):
        logger.warning(f"[SIGNAL] {symbol}: LLM gave invalid levels — recomputing from ATR")
        stop_loss = risk_engine.compute_stop_loss(entry, side, atr)
        take_profit = risk_engine.compute_take_profit(entry, stop_loss, side)

    llm = get_llm()
    logger.info(
        f"[SIGNAL] {symbol}: {signal_str.upper()} | {confidence:.0%} | "
        f"{llm.provider_name}/{llm.model} | "
        f"Entry:{entry:.4f} SL:{stop_loss:.4f} TP:{take_profit:.4f}"
    )

    return TradeSignal(
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


async def generate_signals_batch(
    market_data_map: dict,
    ohlcv_map: dict,
) -> List[TradeSignal]:
    results = await asyncio.gather(
        *[generate_signal(sym, md, ohlcv_map.get(sym, []))
          for sym, md in market_data_map.items()],
        return_exceptions=True,
    )
    signals = []
    for r in results:
        if isinstance(r, TradeSignal):
            signals.append(r)
        elif isinstance(r, Exception):
            logger.error(f"[SIGNAL] Batch error: {r}")
    return signals
