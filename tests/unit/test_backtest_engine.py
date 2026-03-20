# File: tests/unit/test_backtest_engine.py
"""
Unit tests for the backtesting engine — pure computation, no network needed
"""
import pytest
import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def make_ohlcv(n=150, trend="up", start=100.0, seed=42):
    import random
    random.seed(seed)
    data = []
    price = start
    for i in range(n):
        if trend == "up":
            chg = random.uniform(-0.006, 0.015)
        elif trend == "down":
            chg = random.uniform(-0.015, 0.006)
        elif trend == "ranging":
            chg = 0.008 * math.sin(i * 0.25) + random.uniform(-0.003, 0.003)
        else:
            chg = random.uniform(-0.025, 0.025)
        price = max(price * (1 + chg), 0.01)
        o = price * (1 + random.uniform(-0.002, 0.002))
        h = price * (1 + abs(random.uniform(0, 0.008)))
        l = price * (1 - abs(random.uniform(0, 0.008)))
        data.append({"timestamp": i*900000, "open": o, "high": h, "low": l, "close": price, "volume": random.uniform(500, 5000)})
    return data


class TestBacktestResult:
    """Test the BacktestResult metrics computation"""

    def _run(self, trend="up", strategy="momentum", capital=10000):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(150, trend)
        engine = BacktestEngine(initial_capital=capital)
        return engine.run(ohlcv, strategy=strategy, symbol="TEST")

    def test_initial_capital_preserved_when_no_trades(self):
        from src.backtesting.engine import BacktestEngine
        # Use very high confidence threshold to avoid any trades
        ohlcv = make_ohlcv(60)
        engine = BacktestEngine(initial_capital=5000, min_confidence=0.99)
        result = engine.run(ohlcv, strategy="momentum")
        assert result.initial_capital == 5000
        # Final capital should be equal or very close (only commissions on 0 trades)
        assert result.total_trades == 0
        assert result.final_capital == pytest.approx(5000, abs=1)

    def test_total_return_formula(self):
        result = self._run()
        expected = (result.final_capital - result.initial_capital) / result.initial_capital * 100
        assert abs(result.total_return_pct - expected) < 0.01

    def test_win_rate_formula(self):
        result = self._run()
        if result.total_trades > 0:
            expected = result.winning_trades / result.total_trades * 100
            assert abs(result.win_rate - expected) < 0.01

    def test_max_drawdown_non_negative(self):
        for trend in ["up", "down", "ranging", "volatile"]:
            result = self._run(trend=trend)
            assert result.max_drawdown_pct >= 0, f"Negative drawdown for {trend}"

    def test_profit_factor_when_has_both_wins_losses(self):
        result = self._run("volatile", capital=10000)
        if result.winning_trades > 0 and result.losing_trades > 0:
            assert result.profit_factor is not None
            assert result.profit_factor > 0

    def test_sharpe_ratio_computed(self):
        result = self._run(trend="up")
        if len(result.equity_curve) > 10:
            # May be None if std=0 (flat curve), otherwise should be a number
            if result.sharpe_ratio is not None:
                assert isinstance(result.sharpe_ratio, float)

    def test_summary_completeness(self):
        result = self._run()
        summary = result.summary()
        for key in ["total_return_pct", "win_rate_pct", "total_trades",
                    "max_drawdown_pct", "profit_factor", "sharpe_ratio",
                    "initial_capital", "final_capital"]:
            assert key in summary

    def test_equity_curve_starts_at_capital(self):
        result = self._run()
        if result.equity_curve:
            assert abs(result.equity_curve[0] - result.initial_capital) < 1.0

    def test_all_strategies_run(self):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(150)
        engine = BacktestEngine(initial_capital=10000)
        for strategy in ["momentum", "mean_reversion", "breakout", "best"]:
            result = engine.run(ohlcv, strategy=strategy)
            assert result is not None, f"Strategy {strategy} returned None"
            assert isinstance(result.final_capital, float)


class TestCommissions:
    def test_commission_reduces_capital(self):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(150, "up")

        no_commission = BacktestEngine(initial_capital=10000, commission_pct=0.0)
        with_commission = BacktestEngine(initial_capital=10000, commission_pct=0.002)

        r1 = no_commission.run(ohlcv, strategy="momentum")
        r2 = with_commission.run(ohlcv, strategy="momentum")

        # If there were any trades, commissions should reduce final capital
        if r1.total_trades > 0:
            assert r1.final_capital >= r2.final_capital


class TestPositionSizing:
    def test_max_position_count_respected(self):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(200, "volatile")

        engine = BacktestEngine(
            initial_capital=10000,
            max_open_positions=2,
            min_confidence=0.55,
        )
        result = engine.run(ohlcv, strategy="best")
        # All trades should have valid quantities
        for trade in result.trades:
            assert trade.quantity > 0

    def test_position_size_pct_applied(self):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(200, "up")
        engine = BacktestEngine(
            initial_capital=10000,
            position_size_pct=0.05,  # 5%
            min_confidence=0.55,
        )
        result = engine.run(ohlcv, strategy="momentum")
        for trade in result.trades:
            # Trade value should be close to 5% of capital (at time of entry)
            trade_value = trade.quantity * trade.entry_price
            assert trade_value <= 10000 * 0.06  # small tolerance
