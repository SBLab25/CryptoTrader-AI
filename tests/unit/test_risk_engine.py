# File: tests/unit/test_risk_engine.py
"""
Unit tests for the Risk Management Engine
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch
from src.core.models import TradeSignal, Portfolio, SignalStrength, Position, OrderSide
from datetime import datetime


def make_portfolio(
    total_value=10000.0,
    available_balance=10000.0,
    invested_value=0.0,
) -> Portfolio:
    return Portfolio(
        total_value=total_value,
        available_balance=available_balance,
        invested_value=invested_value,
        total_pnl=0.0,
        total_pnl_pct=0.0,
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        open_positions=[],
        is_paper=True,
    )


def make_signal(
    symbol="BTC_USDT",
    signal=SignalStrength.BUY,
    confidence=0.80,
    entry=50000.0,
    stop_loss=49000.0,
    take_profit=52000.0,
) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        reasoning="Test signal",
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


class TestRiskEngine:
    """
    Risk Engine tests — each test gets a fresh engine to avoid state bleed.
    """

    def _fresh_engine(self):
        """Return a fresh RiskEngine instance"""
        # Import fresh to avoid singleton state pollution
        import importlib
        import src.risk.risk_engine as re_module
        engine = re_module.RiskEngine()
        return engine

    def test_approve_valid_trade(self):
        engine = self._fresh_engine()
        signal = make_signal()
        portfolio = make_portfolio()
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is True
        assert result.trade_size > 0

    def test_reject_low_confidence(self):
        engine = self._fresh_engine()
        signal = make_signal(confidence=0.40)
        portfolio = make_portfolio()
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is False
        assert "confidence" in result.reason.lower()

    def test_reject_max_positions_reached(self):
        engine = self._fresh_engine()
        signal = make_signal()
        portfolio = make_portfolio()
        result = engine.assess_trade(signal, portfolio, engine.max_open_positions)
        assert result.approved is False
        assert "position" in result.reason.lower()

    def test_reject_poor_risk_reward(self):
        engine = self._fresh_engine()
        # Entry 50000, SL 49500 (risk=500), TP 50600 (reward=600) → RR=1.2 < 1.5
        signal = make_signal(entry=50000, stop_loss=49500, take_profit=50600)
        portfolio = make_portfolio()
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is False
        assert "risk" in result.reason.lower() or "reward" in result.reason.lower()

    def test_reject_insufficient_balance(self):
        engine = self._fresh_engine()
        signal = make_signal()
        portfolio = make_portfolio(total_value=5.0, available_balance=5.0)
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is False

    def test_pause_on_daily_loss_limit(self):
        engine = self._fresh_engine()
        portfolio = make_portfolio(total_value=10000.0, available_balance=10000.0)
        # Simulate a large daily loss
        engine.update_daily_pnl(-600.0)  # > 5% of 10000
        signal = make_signal()
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is False
        assert engine.is_paused or "daily" in result.reason.lower()

    def test_resume_trading(self):
        engine = self._fresh_engine()
        engine._trading_paused = True
        engine._pause_reason = "Test pause"
        engine.resume_trading()
        assert engine.is_paused is False

    def test_compute_stop_loss_buy(self):
        engine = self._fresh_engine()
        sl = engine.compute_stop_loss(50000, "buy", atr=None)
        # Should be below entry
        assert sl < 50000

    def test_compute_stop_loss_with_atr(self):
        engine = self._fresh_engine()
        sl = engine.compute_stop_loss(50000, "buy", atr=200)
        # ATR-based: 50000 - (200 * 1.5) = 49700
        assert abs(sl - 49700) < 1

    def test_compute_take_profit_rr2(self):
        engine = self._fresh_engine()
        sl = 49000
        entry = 50000
        tp = engine.compute_take_profit(entry, sl, "buy", rr=2.0)
        # Risk = 1000, Reward = 2000 → TP = 52000
        assert abs(tp - 52000) < 1

    def test_trade_size_respects_max_pct(self):
        engine = self._fresh_engine()
        signal = make_signal(entry=50000.0)
        portfolio = make_portfolio(total_value=10000.0, available_balance=10000.0)
        result = engine.assess_trade(signal, portfolio, 0)
        if result.approved:
            trade_value = result.trade_size * signal.entry_price
            max_allowed = 10000.0 * (engine.max_position_size_pct)
            assert trade_value <= max_allowed * 1.01  # small float tolerance

    def test_good_rr_approved(self):
        engine = self._fresh_engine()
        # Entry 100, SL 98 (risk=2), TP 104 (reward=4) → RR=2.0 ✓
        signal = make_signal(entry=100, stop_loss=98, take_profit=104, confidence=0.75)
        portfolio = make_portfolio()
        result = engine.assess_trade(signal, portfolio, 0)
        assert result.approved is True
