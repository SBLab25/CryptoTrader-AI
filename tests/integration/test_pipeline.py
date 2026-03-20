# File: tests/integration/test_pipeline.py
"""
Full pipeline integration tests.
Tests the complete signal → risk → execution → portfolio cycle
without making any external API calls.
"""
import pytest
import asyncio
import math
import random
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_ohlcv(n=150, trend="up", start=100.0, seed=7):
    random.seed(seed)
    data, p = [], start
    for i in range(n):
        chg = {"up": random.uniform(-0.006, 0.018),
               "down": random.uniform(-0.018, 0.006),
               "ranging": 0.008 * math.sin(i * 0.25) + random.uniform(-0.003, 0.003),
               "volatile": random.uniform(-0.03, 0.03)}.get(trend, 0)
        p = max(p * (1 + chg), 0.01)
        data.append({
            "timestamp": i * 900000,
            "open": p * 0.999, "high": p * 1.006,
            "low": p * 0.994, "close": p,
            "volume": random.uniform(800, 6000),
        })
    return data


# ── Strategy → Risk → Paper Engine Pipeline ───────────────────────────────────

class TestStrategyRiskPipeline:

    def test_ta_drives_strategy_in_uptrend(self):
        from src.exchange.indicators import analyze_indicators
        from src.strategies.strategies import select_best_strategy

        ohlcv = make_ohlcv(150, "up")
        indicators = analyze_indicators(ohlcv)
        assert indicators.get("trend") in ["bullish", "neutral"]

        result = select_best_strategy(ohlcv, ohlcv[-1]["close"])
        if result and result.direction:
            assert result.direction != "sell"

    def test_ta_in_downtrend(self):
        from src.exchange.indicators import analyze_indicators
        from src.strategies.strategies import select_best_strategy

        ohlcv = make_ohlcv(150, "down")
        indicators = analyze_indicators(ohlcv)
        assert indicators.get("trend") in ["bearish", "neutral"]

        result = select_best_strategy(ohlcv, ohlcv[-1]["close"])
        if result and result.direction:
            assert result.direction != "buy"

    def test_strategy_levels_always_logical(self):
        from src.strategies.strategies import momentum_strategy, mean_reversion_strategy

        for trend in ["up", "down", "ranging"]:
            ohlcv = make_ohlcv(120, trend, seed=abs(hash(trend)) % 100)
            price = ohlcv[-1]["close"]

            for fn in [momentum_strategy, mean_reversion_strategy]:
                result = fn(ohlcv, price)
                if result and result.direction == "buy":
                    assert result.stop_loss < price
                    assert result.take_profit > price
                elif result and result.direction == "sell":
                    assert result.stop_loss > price
                    assert result.take_profit < price

    def test_paper_engine_full_trade_cycle(self):
        from src.exchange.paper_engine import PaperTradingEngine

        engine = PaperTradingEngine(10000.0)
        initial_usdt = engine.get_balance()["USDT"]

        order = engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        assert order.get("order_id") is not None

        triggered = engine.check_stop_take_profit({"BTC_USDT": 52100})
        assert len(triggered) == 1
        assert triggered[0]["trigger"] == "take_profit"
        assert triggered[0]["pnl"] > 0

    def test_paper_engine_stop_loss_cycle(self):
        from src.exchange.paper_engine import PaperTradingEngine

        engine = PaperTradingEngine(10000.0)
        engine.place_order("ETH_USDT", "buy", 0.1, 3000, 2900, 3200)
        triggered = engine.check_stop_take_profit({"ETH_USDT": 2850})
        assert len(triggered) == 1
        assert triggered[0]["trigger"] == "stop_loss"
        assert triggered[0]["pnl"] < 0

    def test_paper_engine_multiple_symbols_independent(self):
        from src.exchange.paper_engine import PaperTradingEngine

        engine = PaperTradingEngine(10000.0)
        engine.place_order("BTC_USDT", "buy", 0.001, 50000, 49000, 52000)
        engine.place_order("ETH_USDT", "buy", 0.01, 3000, 2900, 3200)

        triggered = engine.check_stop_take_profit({"BTC_USDT": 50500, "ETH_USDT": 3300})
        assert len(triggered) == 1
        assert triggered[0]["symbol"] == "ETH_USDT"

    def test_portfolio_tracks_multiple_trades(self):
        from src.agents.portfolio_agent import PortfolioAgent
        from src.core.models import Trade, OrderSide, OrderStatus

        pa = PortfolioAgent(10000.0)
        trades = []

        for sym, entry, qty in [("BTC_USDT", 50000, 0.001),
                                  ("ETH_USDT", 3000, 0.01),
                                  ("SOL_USDT", 200, 0.5)]:
            t = Trade(symbol=sym, side=OrderSide.BUY, quantity=qty,
                      entry_price=entry, stop_loss=entry * 0.98,
                      take_profit=entry * 1.04, status=OrderStatus.OPEN, is_paper=True)
            pa.record_trade_opened(t, qty * entry)
            trades.append(t)

        assert pa.open_trade_count == 3
        for t in trades:
            pa.record_trade_closed(t, t.entry_price * 1.03, "take_profit")

        assert pa.open_trade_count == 0
        assert pa.win_rate == 100.0
        assert pa.get_performance_stats()["total_pnl"] > 0

    def test_risk_engine_rr_gate(self):
        from src.risk.engine import RiskEngine
        from src.core.models import TradeSignal, Portfolio, SignalStrength

        engine = RiskEngine()
        portfolio = Portfolio(total_value=10000, available_balance=10000,
                              invested_value=0, total_pnl=0, total_pnl_pct=0,
                              daily_pnl=0, daily_pnl_pct=0, open_positions=[], is_paper=True)

        bad = TradeSignal(symbol="X", signal=SignalStrength.BUY, confidence=0.85,
                          reasoning="t", entry_price=100, stop_loss=98, take_profit=102)
        assert not engine.assess_trade(bad, portfolio, 0).approved

        engine2 = RiskEngine()
        good = TradeSignal(symbol="X", signal=SignalStrength.BUY, confidence=0.85,
                           reasoning="t", entry_price=100, stop_loss=98, take_profit=104)
        assert engine2.assess_trade(good, portfolio, 0).approved

    def test_risk_engine_position_sizing(self):
        from src.risk.engine import RiskEngine
        from src.core.models import TradeSignal, Portfolio, SignalStrength

        engine = RiskEngine()
        portfolio = Portfolio(total_value=10000, available_balance=10000,
                              invested_value=0, total_pnl=0, total_pnl_pct=0,
                              daily_pnl=0, daily_pnl_pct=0, open_positions=[], is_paper=True)

        signal = TradeSignal(symbol="X", signal=SignalStrength.BUY, confidence=0.85,
                             reasoning="t", entry_price=100, stop_loss=98, take_profit=104)
        result = engine.assess_trade(signal, portfolio, 0)
        if result.approved:
            assert result.trade_size * signal.entry_price <= 10000 * 0.051


# ── Backtesting End-to-End ────────────────────────────────────────────────────

class TestBacktestEndToEnd:

    def _run(self, trend, strategy, n=200, capital=10000):
        from src.backtesting.engine import BacktestEngine
        return BacktestEngine(capital).run(make_ohlcv(n, trend), strategy=strategy)

    def test_result_fields_always_present(self):
        result = self._run("up", "momentum")
        for key in ["total_return_pct", "max_drawdown_pct", "win_rate_pct",
                    "profit_factor", "sharpe_ratio", "initial_capital", "final_capital"]:
            assert key in result.summary()

    def test_max_drawdown_always_non_negative(self):
        for trend in ["up", "down", "ranging", "volatile"]:
            result = self._run(trend, "best")
            assert result.max_drawdown_pct >= 0

    def test_equity_never_goes_negative(self):
        from src.backtesting.engine import BacktestEngine
        result = BacktestEngine(1000, position_size_pct=0.10).run(
            make_ohlcv(300, "volatile", seed=99), "best"
        )
        for v in result.equity_curve:
            assert v >= 0

    def test_commission_reduces_returns(self):
        from src.backtesting.engine import BacktestEngine
        ohlcv = make_ohlcv(200, "up")
        r_free = BacktestEngine(10000, commission_pct=0.0).run(ohlcv, "momentum")
        r_paid = BacktestEngine(10000, commission_pct=0.005).run(ohlcv, "momentum")
        if r_free.total_trades > 0:
            assert r_free.final_capital >= r_paid.final_capital

    def test_compare_strategies_returns_all_four(self):
        from src.backtesting.engine import compare_strategies
        results = compare_strategies(make_ohlcv(200, "up"))
        assert all(k in results for k in ["momentum", "mean_reversion", "breakout", "best"])

    def test_worst_le_best_trade(self):
        result = self._run("volatile", "best", n=200)
        if result.total_trades >= 2:
            assert result.worst_trade.pnl <= result.best_trade.pnl

    def test_sharpe_not_nan(self):
        result = self._run("up", "momentum", n=300)
        if result.sharpe_ratio is not None:
            assert not math.isnan(result.sharpe_ratio)


# ── TA Indicator Consistency ──────────────────────────────────────────────────

class TestTAConsistency:

    def test_rsi_direction_matches_trend(self):
        from src.exchange.indicators import compute_rsi
        up = [50 + i * 1.5 for i in range(40)]
        assert compute_rsi(up) > 50
        down = [100 - i * 1.5 for i in range(40)]
        assert compute_rsi(down) < 50

    def test_ema_crossover_in_uptrend(self):
        from src.exchange.indicators import analyze_indicators
        ohlcv, p = [], 100.0
        for i in range(60):
            p *= 1.005
            ohlcv.append({"timestamp": i, "open": p * 0.999, "high": p * 1.003,
                          "low": p * 0.997, "close": p, "volume": 1000})
        r = analyze_indicators(ohlcv)
        if r.get("ema_20") and r.get("ema_50"):
            assert r["ema_20"] > r["ema_50"]
            assert r["trend"] == "bullish"

    def test_bollinger_contains_price_mostly(self):
        from src.exchange.indicators import compute_bollinger_bands
        random.seed(0)
        prices = [100.0]
        for _ in range(100):
            prices.append(prices[-1] * (1 + random.gauss(0, 0.01)))

        inside = sum(
            1 for i in range(20, len(prices))
            if (bb := compute_bollinger_bands(prices[:i+1]))
            and bb["lower"] and bb["lower"] <= prices[i] <= bb["upper"]
        )
        assert inside / (len(prices) - 20) >= 0.85

    def test_atr_higher_in_volatile_market(self):
        from src.exchange.indicators import compute_atr
        random.seed(1)

        def gen(vol):
            data, p = [], 100.0
            for _ in range(30):
                p = max(p * (1 + random.gauss(0, 0.01 * vol)), 1.0)
                data.append({"open": p, "high": p * (1 + vol * 0.005),
                             "low": p * (1 - vol * 0.005), "close": p, "volume": 1000})
            return data

        assert compute_atr(gen(5)) > compute_atr(gen(1))


# ── Scheduler Integration ─────────────────────────────────────────────────────

class TestSchedulerIntegration:

    @pytest.mark.asyncio
    async def test_task_fires_at_correct_time(self):
        from src.utils.scheduler import DailyScheduler
        from datetime import datetime
        from unittest.mock import patch

        scheduler = DailyScheduler()
        fired = []
        async def task(): fired.append(True)
        scheduler.register("Test", 0, 0, task)
        scheduler._tasks[0].last_run = None

        with patch("app.utils.scheduler.datetime") as m:
            m.utcnow.return_value = datetime(2025, 1, 1, 0, 0, 10)
            await scheduler._tick()
        assert len(fired) == 1

    @pytest.mark.asyncio
    async def test_exception_does_not_crash_scheduler(self):
        from src.utils.scheduler import DailyScheduler
        from datetime import datetime
        from unittest.mock import patch

        scheduler = DailyScheduler()
        async def bad(): raise ValueError("boom")
        scheduler.register("Bad", 8, 0, bad)
        scheduler._tasks[0].last_run = None

        with patch("app.utils.scheduler.datetime") as m:
            m.utcnow.return_value = datetime(2025, 1, 1, 8, 0, 5)
            await scheduler._tick()  # must not raise

        assert len(scheduler._tasks[0].errors) == 1

    def test_status_has_all_registered_tasks(self):
        from src.utils.scheduler import DailyScheduler
        s = DailyScheduler()
        async def t(): pass
        s.register("A", 8, 0, t)
        s.register("B", 20, 0, t)
        status = s.get_status()
        assert len(status) == 2
        names = {st["name"] for st in status}
        assert names == {"A", "B"}
