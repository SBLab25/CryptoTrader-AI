# File: tests/unit/test_indicators.py
"""
Unit tests for technical analysis tools
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.exchange.indicators import (
    compute_rsi,
    compute_macd,
    compute_bollinger_bands,
    compute_ema,
    compute_sma,
    compute_atr,
    analyze_indicators,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_prices(n=50, start=100.0, trend=0.001):
    """Generate synthetic price series with mild uptrend"""
    import math
    prices = []
    for i in range(n):
        noise = math.sin(i * 0.3) * 0.5
        prices.append(round(start * (1 + trend * i) + noise, 4))
    return prices


def make_ohlcv(n=50):
    prices = make_prices(n)
    candles = []
    for i, p in enumerate(prices):
        candles.append({
            "timestamp": i * 300000,
            "open": p * 0.999,
            "high": p * 1.005,
            "low": p * 0.995,
            "close": p,
            "volume": 1000 + i * 10,
        })
    return candles


# ── RSI Tests ─────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_returns_float_for_sufficient_data(self):
        prices = make_prices(30)
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert isinstance(rsi, float)

    def test_rsi_range(self):
        prices = make_prices(30)
        rsi = compute_rsi(prices)
        assert 0 <= rsi <= 100

    def test_rsi_none_for_insufficient_data(self):
        prices = make_prices(10)
        rsi = compute_rsi(prices, period=14)
        assert rsi is None

    def test_rsi_overbought_rising_prices(self):
        # Strongly rising prices → RSI should be high (overbought)
        prices = [100 + i * 2 for i in range(30)]
        rsi = compute_rsi(prices)
        assert rsi > 70

    def test_rsi_oversold_falling_prices(self):
        # Strongly falling prices → RSI should be low (oversold)
        prices = [200 - i * 2 for i in range(30)]
        rsi = compute_rsi(prices)
        assert rsi < 30


# ── MACD Tests ────────────────────────────────────────────────────────────────

class TestMACD:
    def test_macd_structure(self):
        prices = make_prices(60)
        result = compute_macd(prices)
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result

    def test_macd_returns_none_for_insufficient_data(self):
        prices = make_prices(10)
        result = compute_macd(prices)
        assert result["macd"] is None

    def test_macd_bullish_crossover(self):
        # Fast rising prices → positive MACD histogram
        prices = [50 + i * 1.5 for i in range(60)]
        result = compute_macd(prices)
        if result["histogram"] is not None:
            assert result["histogram"] > 0


# ── Bollinger Bands Tests ─────────────────────────────────────────────────────

class TestBollingerBands:
    def test_bb_structure(self):
        prices = make_prices(30)
        bb = compute_bollinger_bands(prices)
        assert all(k in bb for k in ["upper", "middle", "lower", "pct_b", "bandwidth"])

    def test_bb_upper_gt_lower(self):
        prices = make_prices(30)
        bb = compute_bollinger_bands(prices)
        assert bb["upper"] > bb["lower"]

    def test_bb_pct_b_range(self):
        prices = make_prices(30)
        bb = compute_bollinger_bands(prices)
        # pct_b can be slightly outside [0,1] for extreme moves, but should be near
        assert -0.5 <= bb["pct_b"] <= 1.5

    def test_bb_insufficient_data(self):
        prices = make_prices(5)
        bb = compute_bollinger_bands(prices, period=20)
        assert bb["upper"] is None


# ── EMA / SMA Tests ───────────────────────────────────────────────────────────

class TestMovingAverages:
    def test_ema_length(self):
        prices = make_prices(30)
        ema = compute_ema(prices, 10)
        assert len(ema) == len(prices) - 10 + 1

    def test_sma_values(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        sma = compute_sma(prices, 3)
        assert abs(sma[0] - 2.0) < 0.001
        assert abs(sma[-1] - 4.0) < 0.001

    def test_ema_empty_for_insufficient_data(self):
        ema = compute_ema([1.0, 2.0], period=10)
        assert ema == []


# ── ATR Tests ─────────────────────────────────────────────────────────────────

class TestATR:
    def test_atr_returns_positive(self):
        ohlcv = make_ohlcv(30)
        atr = compute_atr(ohlcv)
        assert atr is not None
        assert atr > 0

    def test_atr_none_insufficient_data(self):
        ohlcv = make_ohlcv(5)
        atr = compute_atr(ohlcv, period=14)
        assert atr is None

    def test_atr_high_volatility(self):
        # Wide H-L ranges → large ATR
        ohlcv = [{"open": 100, "high": 120, "low": 80, "close": 100, "volume": 1000}
                 for _ in range(20)]
        atr = compute_atr(ohlcv)
        assert atr > 15  # True range ~20-40 each bar


# ── Full Indicator Analysis ───────────────────────────────────────────────────

class TestAnalyzeIndicators:
    def test_analyze_returns_dict(self):
        ohlcv = make_ohlcv(60)
        result = analyze_indicators(ohlcv)
        assert isinstance(result, dict)

    def test_analyze_has_required_keys(self):
        ohlcv = make_ohlcv(60)
        result = analyze_indicators(ohlcv)
        required = ["current_price", "rsi", "macd", "bollinger_bands", "trend",
                    "technical_bias", "signal_strength"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_analyze_bias_is_valid(self):
        ohlcv = make_ohlcv(60)
        result = analyze_indicators(ohlcv)
        assert result["technical_bias"] in ["bullish", "bearish", "neutral"]

    def test_analyze_insufficient_data(self):
        ohlcv = make_ohlcv(10)
        result = analyze_indicators(ohlcv)
        assert "error" in result

    def test_analyze_bullish_trend(self):
        # Strong uptrend data
        ohlcv = []
        for i in range(60):
            p = 100 + i * 2
            ohlcv.append({"timestamp": i, "open": p-1, "high": p+1, "low": p-2, "close": p, "volume": 1000})
        result = analyze_indicators(ohlcv)
        assert result["trend"] in ["bullish", "neutral"]  # EMA 20 > 50 in uptrend
