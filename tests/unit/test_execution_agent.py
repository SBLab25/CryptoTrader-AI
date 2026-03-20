# File: tests/unit/test_execution_agent.py
"""
Unit tests for Execution Agent and Daily Scheduler
"""
import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ── Execution Agent Tests ─────────────────────────────────────────────────────

class TestExecutionAgent:
    """Test order execution logic without live exchange calls"""

    def _make_engine(self, capital=10000.0):
        from src.exchange.paper_engine import PaperTradingEngine
        return PaperTradingEngine(capital)

    def _make_signal(self, symbol="BTC_USDT", conf=0.80, entry=50000, sl=49000, tp=52000):
        """Build a minimal signal-like object"""
        class MockSignal:
            id = "test-signal-id"
            signal = type('S', (), {'value': 'buy'})()
            confidence = conf
            entry_price = entry
            stop_loss = sl
            take_profit = tp
        obj = MockSignal()
        obj.symbol = symbol
        return obj

    def _make_risk(self, trade_size=0.01, approved=True):
        class MockRisk:
            pass
        r = MockRisk()
        r.trade_size = trade_size
        r.approved = approved
        return r

    @pytest.mark.asyncio
    async def test_execute_paper_trade_success(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)
        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.01)

        trade = await agent.execute_trade(signal, risk, is_paper=True)
        assert trade is not None
        assert trade.symbol == "BTC_USDT"
        assert trade.quantity == pytest.approx(0.01, abs=0.0001)

    @pytest.mark.asyncio
    async def test_execute_zero_size_returns_none(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)
        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.0)

        trade = await agent.execute_trade(signal, risk, is_paper=True)
        assert trade is None

    @pytest.mark.asyncio
    async def test_fill_callback_fired(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)

        filled_trades = []
        async def on_fill(t):
            filled_trades.append(t)
        agent.on_fill(on_fill)

        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.001)
        await agent.execute_trade(signal, risk, is_paper=True)

        assert len(filled_trades) == 1

    @pytest.mark.asyncio
    async def test_stats_increment_on_success(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)
        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.001)

        await agent.execute_trade(signal, risk, is_paper=True)
        assert agent.stats["orders_placed"] == 1
        assert agent.stats["orders_filled"] == 1

    @pytest.mark.asyncio
    async def test_insufficient_balance_returns_none(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine(capital=10.0)  # Only $10
        agent = ExecutionAgent(engine)
        signal = self._make_signal(entry=50000)
        risk = self._make_risk(trade_size=1.0)  # Would cost $50,000

        trade = await agent.execute_trade(signal, risk, is_paper=True)
        assert trade is None
        assert agent.stats["orders_rejected"] == 1

    @pytest.mark.asyncio
    async def test_pending_orders_tracked(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)
        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.001)

        await agent.execute_trade(signal, risk, is_paper=True)
        assert agent.pending_count == 1

    @pytest.mark.asyncio
    async def test_close_trade_paper(self):
        from src.agents.execution_agent import ExecutionAgent
        from src.core.models import Trade, OrderSide, OrderStatus
        engine = self._make_engine()
        agent = ExecutionAgent(engine)

        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.001)
        trade = await agent.execute_trade(signal, risk, is_paper=True)
        assert trade is not None

        success = await agent.close_trade(trade, 52000.0, "take_profit", is_paper=True)
        assert success is True
        assert agent.pending_count == 0

    @pytest.mark.asyncio
    async def test_timeout_monitor(self):
        from src.agents.execution_agent import ExecutionAgent
        engine = self._make_engine()
        agent = ExecutionAgent(engine)
        agent._config.order_timeout_sec = 0  # Immediate timeout

        signal = self._make_signal()
        risk = self._make_risk(trade_size=0.001)
        await agent.execute_trade(signal, risk, is_paper=True)
        assert agent.pending_count == 1

        # Manually backdate the placed_at to trigger timeout
        for meta in agent._pending_orders.values():
            meta["placed_at"] = datetime.utcnow() - timedelta(seconds=60)

        timed_out = await agent.monitor_pending_timeouts()
        assert len(timed_out) == 1
        assert agent.pending_count == 0


# ── Scheduler Tests ───────────────────────────────────────────────────────────

class TestDailyScheduler:
    @pytest.mark.asyncio
    async def test_register_task(self):
        from src.utils.scheduler import DailyScheduler
        scheduler = DailyScheduler()
        called = []

        async def my_task():
            called.append(True)

        scheduler.register("Test Task", hour=0, minute=0, callback=my_task)
        assert len(scheduler._tasks) == 1
        assert scheduler._tasks[0].name == "Test Task"

    @pytest.mark.asyncio
    async def test_task_fires_at_correct_time(self):
        from src.utils.scheduler import DailyScheduler
        scheduler = DailyScheduler()
        fired = []

        async def midnight_task():
            fired.append(True)

        scheduler.register("Midnight", hour=0, minute=0, callback=midnight_task)

        # Simulate exactly midnight
        midnight = datetime(2025, 1, 1, 0, 0, 30)
        scheduler._tasks[0].last_run = None

        # Manually call _tick with mocked time
        with patch('app.utils.scheduler.datetime') as mock_dt:
            mock_dt.utcnow.return_value = midnight
            # Test is_due
            assert scheduler._tasks[0].is_due(midnight)

    @pytest.mark.asyncio
    async def test_task_not_double_fired(self):
        from src.utils.scheduler import DailyScheduler
        scheduler = DailyScheduler()
        fired = []

        async def task():
            fired.append(True)

        scheduler.register("Test", hour=12, minute=0, callback=task)
        now = datetime(2025, 1, 1, 12, 0, 30)

        # First call should fire
        assert scheduler._tasks[0].is_due(now)
        scheduler._tasks[0].last_run = now

        # Second call within same minute should NOT fire
        assert not scheduler._tasks[0].is_due(now)

    @pytest.mark.asyncio
    async def test_task_error_does_not_crash_scheduler(self):
        from src.utils.scheduler import DailyScheduler
        scheduler = DailyScheduler()

        async def failing_task():
            raise ValueError("Test error")

        scheduler.register("Failing", hour=0, minute=0, callback=failing_task)

        now = datetime(2025, 1, 1, 0, 0, 0)
        # Should not raise
        with patch('app.utils.scheduler.datetime') as mock_dt:
            mock_dt.utcnow.return_value = now
            await scheduler._tick()

        assert len(scheduler._tasks[0].errors) == 1

    def test_get_status(self):
        from src.utils.scheduler import DailyScheduler
        scheduler = DailyScheduler()

        async def t():
            pass

        scheduler.register("A", 8, 0, t)
        scheduler.register("B", 20, 0, t)
        status = scheduler.get_status()
        assert len(status) == 2
        assert status[0]["name"] == "A"
        assert status[1]["scheduled_utc"] == "20:00"
