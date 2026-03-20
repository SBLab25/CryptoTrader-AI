# File: src/strategies/strategies.py
"""
Trading Strategies
Each strategy is a pure function: takes market data + indicators → returns a signal dict.
The Signal Agent selects which strategy to apply per symbol based on market conditions.
"""
from typing import Optional, Dict, List
from src.exchange.indicators import analyze_indicators
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Strategy Base ─────────────────────────────────────────────────────────────

class StrategyResult:
    def __init__(
        self,
        direction: Optional[str],  # "buy" | "sell" | None
        confidence: float,
        stop_loss: float,
        take_profit: float,
        reasoning: str,
        strategy_name: str,
    ):
        self.direction = direction
        self.confidence = confidence
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.reasoning = reasoning
        self.strategy_name = strategy_name

    @property
    def is_actionable(self) -> bool:
        return self.direction is not None and self.confidence >= 0.55


# ── Strategy 1: Momentum ──────────────────────────────────────────────────────

def momentum_strategy(
    ohlcv: List[dict],
    current_price: float,
    atr: Optional[float] = None,
) -> StrategyResult:
    """
    Momentum strategy: ride strong trends using EMA crossover + MACD.

    Entry conditions:
    - BUY: EMA20 crosses above EMA50, MACD histogram positive, RSI 45-65
    - SELL: EMA20 crosses below EMA50, MACD histogram negative, RSI 35-55

    Stop-loss: 1.5x ATR below entry
    Take-profit: 3x ATR above entry (2:1 R:R minimum)
    """
    if len(ohlcv) < 55:
        return StrategyResult(None, 0.0, current_price * 0.98, current_price * 1.04,
                              "Insufficient data", "momentum")

    indicators = analyze_indicators(ohlcv)
    rsi = indicators.get("rsi")
    macd = indicators.get("macd", {})
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")
    atr_val = atr or indicators.get("atr") or current_price * 0.02

    if not all([rsi, ema_20, ema_50, macd.get("histogram") is not None]):
        return StrategyResult(None, 0.0, current_price * 0.98, current_price * 1.04,
                              "Missing indicators", "momentum")

    histogram = macd["histogram"]
    direction = None
    confidence = 0.0
    reason_parts = []

    # EMA crossover
    ema_bull = ema_20 > ema_50
    ema_bear = ema_20 < ema_50

    if ema_bull and histogram > 0 and 45 <= rsi <= 70:
        direction = "buy"
        confidence = 0.60
        reason_parts.append(f"EMA20 ({ema_20:.2f}) above EMA50 ({ema_50:.2f})")
        reason_parts.append(f"MACD histogram positive ({histogram:.4f})")
        reason_parts.append(f"RSI in momentum zone ({rsi:.1f})")
        # Boost on strong conditions
        if rsi < 60 and histogram > 0:
            confidence += 0.10
        if indicators.get("volume_surge"):
            confidence += 0.08
            reason_parts.append("Volume surge confirming move")

    elif ema_bear and histogram < 0 and 30 <= rsi <= 55:
        direction = "sell"
        confidence = 0.60
        reason_parts.append(f"EMA20 ({ema_20:.2f}) below EMA50 ({ema_50:.2f})")
        reason_parts.append(f"MACD histogram negative ({histogram:.4f})")
        reason_parts.append(f"RSI in bearish zone ({rsi:.1f})")
        if indicators.get("volume_surge"):
            confidence += 0.08

    # Compute levels
    sl_distance = atr_val * 1.5
    tp_distance = atr_val * 3.0

    if direction == "buy":
        stop_loss = current_price - sl_distance
        take_profit = current_price + tp_distance
    elif direction == "sell":
        stop_loss = current_price + sl_distance
        take_profit = current_price - tp_distance
    else:
        stop_loss = current_price * 0.98
        take_profit = current_price * 1.04

    return StrategyResult(
        direction=direction,
        confidence=min(confidence, 0.90),
        stop_loss=round(stop_loss, 8),
        take_profit=round(take_profit, 8),
        reasoning="; ".join(reason_parts) if reason_parts else "No momentum signal",
        strategy_name="momentum",
    )


# ── Strategy 2: Mean Reversion ────────────────────────────────────────────────

def mean_reversion_strategy(
    ohlcv: List[dict],
    current_price: float,
    atr: Optional[float] = None,
) -> StrategyResult:
    """
    Mean reversion: buy oversold bounces, sell overbought exhaustion.

    Entry conditions:
    - BUY: RSI < 30, price touches lower Bollinger Band, not in strong downtrend
    - SELL: RSI > 70, price touches upper Bollinger Band, not in strong uptrend

    Stop-loss: beyond the band extreme
    Take-profit: at middle band (SMA 20)
    """
    if len(ohlcv) < 25:
        return StrategyResult(None, 0.0, current_price * 0.98, current_price * 1.04,
                              "Insufficient data", "mean_reversion")

    indicators = analyze_indicators(ohlcv)
    rsi = indicators.get("rsi")
    bb = indicators.get("bollinger_bands", {})
    atr_val = atr or indicators.get("atr") or current_price * 0.015

    if not rsi or not bb.get("lower") or not bb.get("upper"):
        return StrategyResult(None, 0.0, current_price * 0.98, current_price * 1.04,
                              "Missing BB/RSI", "mean_reversion")

    pct_b = bb.get("pct_b", 0.5)
    middle = bb.get("middle", current_price)
    lower = bb["lower"]
    upper = bb["upper"]
    trend = indicators.get("trend", "neutral")
    direction = None
    confidence = 0.0
    reason_parts = []

    # Oversold bounce
    if rsi < 32 and pct_b < 0.15 and trend != "bearish":
        direction = "buy"
        confidence = 0.62
        reason_parts.append(f"RSI oversold ({rsi:.1f})")
        reason_parts.append(f"Price near lower Bollinger Band (BB%: {pct_b:.2f})")
        if rsi < 25:
            confidence += 0.10
            reason_parts.append("Extreme oversold — high reversion probability")
        if indicators.get("volume_surge"):
            confidence += 0.07
            reason_parts.append("Volume surge suggests capitulation bottom")

    # Overbought reversal
    elif rsi > 68 and pct_b > 0.85 and trend != "bullish":
        direction = "sell"
        confidence = 0.62
        reason_parts.append(f"RSI overbought ({rsi:.1f})")
        reason_parts.append(f"Price near upper Bollinger Band (BB%: {pct_b:.2f})")
        if rsi > 75:
            confidence += 0.10
            reason_parts.append("Extreme overbought — reversion likely")

    # Compute levels
    if direction == "buy":
        stop_loss = lower - (atr_val * 0.5)   # Just below lower band
        take_profit = middle                    # Return to mean
    elif direction == "sell":
        stop_loss = upper + (atr_val * 0.5)
        take_profit = middle
    else:
        stop_loss = current_price * 0.98
        take_profit = current_price * 1.04

    return StrategyResult(
        direction=direction,
        confidence=min(confidence, 0.88),
        stop_loss=round(stop_loss, 8),
        take_profit=round(take_profit, 8),
        reasoning="; ".join(reason_parts) if reason_parts else "No mean reversion signal",
        strategy_name="mean_reversion",
    )


# ── Strategy 3: Breakout ──────────────────────────────────────────────────────

def breakout_strategy(
    ohlcv: List[dict],
    current_price: float,
    atr: Optional[float] = None,
) -> StrategyResult:
    """
    Breakout: detect price breaking out of a consolidation range with volume.

    Entry conditions:
    - BUY: price breaks above 20-period high with volume surge + low Bollinger bandwidth before
    - SELL: price breaks below 20-period low with volume surge

    Stop-loss: back inside the range (previous high/low)
    Take-profit: 2x ATR beyond breakout level
    """
    if len(ohlcv) < 25:
        return StrategyResult(None, 0.0, current_price * 0.98, current_price * 1.04,
                              "Insufficient data", "breakout")

    indicators = analyze_indicators(ohlcv)
    atr_val = atr or indicators.get("atr") or current_price * 0.015
    bb = indicators.get("bollinger_bands", {})
    bandwidth = bb.get("bandwidth", 1.0)

    closes = [c["close"] for c in ohlcv]
    highs = [c["high"] for c in ohlcv]
    lows = [c["low"] for c in ohlcv]

    period_high = max(highs[-21:-1])  # 20-bar high (exclude current)
    period_low = min(lows[-21:-1])
    volume_surge = indicators.get("volume_surge", False)

    direction = None
    confidence = 0.0
    reason_parts = []

    # Breakout requires low bandwidth (consolidation) before the move
    was_consolidating = bandwidth < 0.04

    if current_price > period_high and volume_surge:
        direction = "buy"
        confidence = 0.65
        reason_parts.append(f"Bullish breakout above {period_high:.4f}")
        reason_parts.append("Volume confirming breakout")
        if was_consolidating:
            confidence += 0.10
            reason_parts.append("Prior low-bandwidth consolidation — strong breakout")
        rsi = indicators.get("rsi")
        if rsi and rsi > 55:
            confidence += 0.05

    elif current_price < period_low and volume_surge:
        direction = "sell"
        confidence = 0.65
        reason_parts.append(f"Bearish breakdown below {period_low:.4f}")
        reason_parts.append("Volume confirming breakdown")
        if was_consolidating:
            confidence += 0.10

    # Levels
    if direction == "buy":
        stop_loss = period_high * 0.995   # Just inside the old resistance
        take_profit = current_price + (atr_val * 2.5)
    elif direction == "sell":
        stop_loss = period_low * 1.005
        take_profit = current_price - (atr_val * 2.5)
    else:
        stop_loss = current_price * 0.98
        take_profit = current_price * 1.04

    return StrategyResult(
        direction=direction,
        confidence=min(confidence, 0.88),
        stop_loss=round(stop_loss, 8),
        take_profit=round(take_profit, 8),
        reasoning="; ".join(reason_parts) if reason_parts else "No breakout signal",
        strategy_name="breakout",
    )


# ── Strategy Selector ─────────────────────────────────────────────────────────

def select_best_strategy(
    ohlcv: List[dict],
    current_price: float,
    atr: Optional[float] = None,
) -> Optional[StrategyResult]:
    """
    Run all strategies and return the one with the highest confidence,
    provided it is actionable (direction set + confidence >= 0.55).
    """
    results = []
    for fn in [momentum_strategy, mean_reversion_strategy, breakout_strategy]:
        try:
            result = fn(ohlcv, current_price, atr)
            if result.is_actionable:
                results.append(result)
                logger.debug(f"[STRATEGY] {result.strategy_name}: {result.direction} "
                             f"conf={result.confidence:.2f}")
        except Exception as e:
            logger.error(f"[STRATEGY] Error in {fn.__name__}: {e}")

    if not results:
        return None

    # Return highest confidence actionable result
    return max(results, key=lambda r: r.confidence)
