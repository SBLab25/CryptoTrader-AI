# File: src/exchange/indicators.py
"""
Technical Analysis Tools
Computes RSI, MACD, Bollinger Bands, EMA, ATR from OHLCV data
"""
from typing import List, Dict, Optional, Tuple
import math


def compute_ema(prices: List[float], period: int) -> List[float]:
    """Exponential Moving Average"""
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def compute_sma(prices: List[float], period: int) -> List[float]:
    """Simple Moving Average"""
    return [
        sum(prices[i:i+period]) / period
        for i in range(len(prices) - period + 1)
    ]


def compute_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Relative Strength Index
    Returns latest RSI value (0-100)
    """
    if len(prices) < period + 1:
        return None
    
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, Optional[float]]:
    """
    MACD (Moving Average Convergence Divergence)
    Returns: macd_line, signal_line, histogram
    """
    if len(prices) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}

    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)

    # Align lengths
    min_len = min(len(ema_fast), len(ema_slow))
    macd_line = [
        ema_fast[-(min_len - i)] - ema_slow[-(min_len - i)]
        for i in range(min_len)
    ]

    if len(macd_line) < signal:
        return {"macd": None, "signal": None, "histogram": None}

    signal_line = compute_ema(macd_line, signal)
    latest_macd = macd_line[-1]
    latest_signal = signal_line[-1] if signal_line else None
    histogram = (latest_macd - latest_signal) if latest_signal is not None else None

    return {
        "macd": round(latest_macd, 6),
        "signal": round(latest_signal, 6) if latest_signal else None,
        "histogram": round(histogram, 6) if histogram else None,
    }


def compute_bollinger_bands(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, Optional[float]]:
    """
    Bollinger Bands
    Returns: upper, middle (SMA), lower, %B, bandwidth
    """
    if len(prices) < period:
        return {"upper": None, "middle": None, "lower": None, "pct_b": None, "bandwidth": None}

    sma_values = compute_sma(prices, period)
    middle = sma_values[-1]
    recent = prices[-period:]
    std = math.sqrt(sum((p - middle) ** 2 for p in recent) / period)
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    current = prices[-1]
    pct_b = (current - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
    bandwidth = (upper - lower) / middle if middle != 0 else 0

    return {
        "upper": round(upper, 6),
        "middle": round(middle, 6),
        "lower": round(lower, 6),
        "pct_b": round(pct_b, 4),
        "bandwidth": round(bandwidth, 4),
    }


def compute_atr(ohlcv: List[dict], period: int = 14) -> Optional[float]:
    """
    Average True Range — measures volatility
    ohlcv: list of {"open", "high", "low", "close", "volume"}
    """
    if len(ohlcv) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i]["high"]
        low = ohlcv[i]["low"]
        prev_close = ohlcv[i-1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[-period:]) / period
    return round(atr, 6)


def compute_volume_sma(volumes: List[float], period: int = 20) -> Optional[float]:
    """Volume Simple Moving Average"""
    if len(volumes) < period:
        return None
    return round(sum(volumes[-period:]) / period, 2)


def analyze_indicators(ohlcv: List[dict]) -> Dict:
    """
    Run all indicators on OHLCV data
    Returns a consolidated indicator dict with trading interpretation
    """
    if not ohlcv or len(ohlcv) < 30:
        return {"error": "Insufficient data (need 30+ candles)"}

    closes = [c["close"] for c in ohlcv]
    volumes = [c["volume"] for c in ohlcv]

    rsi = compute_rsi(closes)
    macd = compute_macd(closes)
    bb = compute_bollinger_bands(closes)
    atr = compute_atr(ohlcv)
    vol_sma = compute_volume_sma(volumes)
    ema_20 = compute_ema(closes, 20)
    ema_50 = compute_ema(closes, 50)
    ema_200 = compute_ema(closes, 200) if len(closes) >= 200 else []

    current_price = closes[-1]
    current_volume = volumes[-1]

    # Trend determination
    trend = "neutral"
    if ema_20 and ema_50:
        if ema_20[-1] > ema_50[-1]:
            trend = "bullish"
        elif ema_20[-1] < ema_50[-1]:
            trend = "bearish"

    # Volume confirmation
    volume_surge = (current_volume > vol_sma * 1.5) if vol_sma else False

    # Signal scoring
    bull_signals = 0
    bear_signals = 0

    if rsi is not None:
        if rsi < 30:
            bull_signals += 2  # Oversold = potential buy
        elif rsi > 70:
            bear_signals += 2  # Overbought = potential sell
        elif rsi < 50:
            bear_signals += 1
        else:
            bull_signals += 1

    if macd["histogram"] is not None:
        if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
            bull_signals += 2
        elif macd["histogram"] < 0:
            bear_signals += 2

    if bb["pct_b"] is not None:
        if bb["pct_b"] < 0.2:
            bull_signals += 1  # Near lower band
        elif bb["pct_b"] > 0.8:
            bear_signals += 1  # Near upper band

    if trend == "bullish":
        bull_signals += 2
    elif trend == "bearish":
        bear_signals += 2

    total = bull_signals + bear_signals
    if total > 0:
        bias = "bullish" if bull_signals > bear_signals else "bearish"
        strength = abs(bull_signals - bear_signals) / total
    else:
        bias = "neutral"
        strength = 0.0

    return {
        "current_price": current_price,
        "rsi": rsi,
        "macd": macd,
        "bollinger_bands": bb,
        "atr": atr,
        "ema_20": round(ema_20[-1], 6) if ema_20 else None,
        "ema_50": round(ema_50[-1], 6) if ema_50 else None,
        "ema_200": round(ema_200[-1], 6) if ema_200 else None,
        "trend": trend,
        "volume_surge": volume_surge,
        "volume_vs_avg": round(current_volume / vol_sma, 2) if vol_sma else None,
        "technical_bias": bias,
        "signal_strength": round(strength, 2),
        "bull_score": bull_signals,
        "bear_score": bear_signals,
    }
