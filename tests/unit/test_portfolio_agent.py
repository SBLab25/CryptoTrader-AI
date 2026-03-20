# File: tests/unit/test_portfolio_agent.py
"""
Unit tests for Portfolio Agent
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.agents.portfolio_agent import PortfolioAgent
from src.core.models import Trade, OrderSide, OrderStatus


def make_trade(
    symbol="BTC_USDT",
    side=OrderSide.BUY,
    quantity=0.01,
    entry_price=50000.0,
    stop_loss=49000.0,
    take_profit=52000.0,
) -> Trade:
    return Trade(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status=OrderStatus.OPEN,
        exchange_order_id=f"TEST-{symbol}-{side.value}",
        is_paper=True,
    )


class TestPortfolioAgent:
    def setup_method(self):
        self.agent = PortfolioAgent(initial_capital=10000.0)

    def test_initial_state(self):
        snapshot = self.agent.get_portfolio_snapshot({})
        assert snapshot.total_value == 10000.0
        assert snapshot.available_balance == 10000.0
        assert len(snapshot.open_positions) == 0

    def test_record_trade_opened(self):
        trade = make_trade()
        cost = trade.quantity * trade.entry_price  # 0.01 * 50000 = 500
        self.agent.record_trade_opened(trade, cost)
        assert self.agent.open_trade_count == 1
        snapshot = self.agent.get_portfolio_snapshot({"BTC_USDT": 50000.0})
        assert abs(snapshot.available_balance - 9500.0) < 1.0

    def test_record_trade_closed_profit(self):
        trade = make_trade()
        cost = trade.quantity * trade.entry_price
        self.agent.record_trade_opened(trade, cost)
        # Close at take profit (52000)
        self.agent.record_trade_closed(trade, 52000.0, "take_profit")
        assert self.agent.open_trade_count == 0
        assert trade.pnl == pytest.approx(20.0, abs=0.01)  # (52000-50000)*0.01

    def test_record_trade_closed_loss(self):
        trade = make_trade()
        cost = trade.quantity * trade.entry_price
        self.agent.record_trade_opened(trade, cost)
        # Close at stop loss (49000)
        self.agent.record_trade_closed(trade, 49000.0, "stop_loss")
        assert trade.pnl == pytest.approx(-10.0, abs=0.01)  # (49000-50000)*0.01

    def test_portfolio_unrealized_pnl(self):
        trade = make_trade()
        cost = trade.quantity * trade.entry_price
        self.agent.record_trade_opened(trade, cost)
        # Price went up to 51000
        snapshot = self.agent.get_portfolio_snapshot({"BTC_USDT": 51000.0})
        assert len(snapshot.open_positions) == 1
        pos = snapshot.open_positions[0]
        assert pos.unrealized_pnl == pytest.approx(10.0, abs=0.01)  # (51000-50000)*0.01

    def test_win_rate_all_wins(self):
        for i in range(3):
            trade = make_trade(symbol=f"COIN{i}_USDT", quantity=0.01, entry_price=100.0)
            self.agent.record_trade_opened(trade, 1.0)
            self.agent.record_trade_closed(trade, 110.0, "take_profit")
        assert self.agent.win_rate == 100.0

    def test_win_rate_mixed(self):
        wins, losses = 3, 1
        for i in range(wins):
            t = make_trade(symbol=f"WIN{i}_USDT", quantity=0.01, entry_price=100.0)
            self.agent.record_trade_opened(t, 1.0)
            self.agent.record_trade_closed(t, 110.0, "take_profit")
        for i in range(losses):
            t = make_trade(symbol=f"LOSE{i}_USDT", quantity=0.01, entry_price=100.0)
            self.agent.record_trade_opened(t, 1.0)
            self.agent.record_trade_closed(t, 95.0, "stop_loss")
        assert self.agent.win_rate == 75.0

    def test_performance_stats(self):
        trade = make_trade()
        self.agent.record_trade_opened(trade, trade.quantity * trade.entry_price)
        self.agent.record_trade_closed(trade, 52000.0, "take_profit")
        stats = self.agent.get_performance_stats()
        assert stats["total_trades"] == 1
        assert stats["winning_trades"] == 1
        assert stats["total_pnl"] > 0

    def test_multiple_open_positions(self):
        for sym in ["BTC_USDT", "ETH_USDT", "SOL_USDT"]:
            t = make_trade(symbol=sym, entry_price=100.0)
            self.agent.record_trade_opened(t, t.quantity * t.entry_price)
        assert self.agent.open_trade_count == 3

    def test_total_value_increases_with_profit(self):
        trade = make_trade(quantity=0.1, entry_price=1000.0)
        cost = trade.quantity * trade.entry_price  # 100 USDT
        self.agent.record_trade_opened(trade, cost)
        self.agent.record_trade_closed(trade, 1200.0, "take_profit")
        snapshot = self.agent.get_portfolio_snapshot({})
        # Started with 10000, made 0.1*(1200-1000) = 20 profit
        assert snapshot.total_value == pytest.approx(10020.0, abs=1.0)
