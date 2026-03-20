# File: tests/unit/test_paper_engine.py
"""
Unit tests for Paper Trading Engine
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.exchange.paper_engine import PaperTradingEngine


class TestPaperTradingEngine:
    def setup_method(self):
        self.engine = PaperTradingEngine(initial_capital=10000.0)

    def test_initial_balance(self):
        assert self.engine.get_balance()["USDT"] == 10000.0

    def test_buy_order_deducts_balance(self):
        result = self.engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        assert result["order_id"] is not None
        assert self.engine.get_balance()["USDT"] == pytest.approx(9500.0, abs=1)
        assert self.engine.get_balance().get("BTC", 0) == pytest.approx(0.01, abs=0.0001)

    def test_insufficient_balance_rejected(self):
        result = self.engine.place_order("BTC_USDT", "buy", 1.0, 50000, 49000, 52000)
        assert "error" in result

    def test_stop_loss_triggered(self):
        order = self.engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        order_id = order["order_id"]
        # Price drops to stop loss
        triggered = self.engine.check_stop_take_profit({"BTC_USDT": 48900})
        assert len(triggered) == 1
        assert triggered[0]["trigger"] == "stop_loss"
        assert triggered[0]["pnl"] < 0

    def test_take_profit_triggered(self):
        order = self.engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        triggered = self.engine.check_stop_take_profit({"BTC_USDT": 52100})
        assert len(triggered) == 1
        assert triggered[0]["trigger"] == "take_profit"
        assert triggered[0]["pnl"] > 0

    def test_no_trigger_in_range(self):
        self.engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        triggered = self.engine.check_stop_take_profit({"BTC_USDT": 50500})
        assert len(triggered) == 0

    def test_close_position_updates_balance(self):
        order = self.engine.place_order("BTC_USDT", "buy", 0.01, 50000, 49000, 52000)
        order_id = order["order_id"]
        balance_before = self.engine.get_balance().get("USDT", 0)
        self.engine.close_position(order_id, 51000)
        balance_after = self.engine.get_balance().get("USDT", 0)
        # Should have gained: (51000-50000)*0.01 = 10 USDT
        assert balance_after > balance_before

    def test_order_counter_increments(self):
        o1 = self.engine.place_order("BTC_USDT", "buy", 0.001, 50000, 49000, 52000)
        o2 = self.engine.place_order("ETH_USDT", "buy", 0.01, 3000, 2900, 3200)
        assert o1["order_id"] != o2["order_id"]

    def test_multiple_symbols(self):
        self.engine.place_order("BTC_USDT", "buy", 0.001, 50000, 49000, 52000)
        self.engine.place_order("ETH_USDT", "buy", 0.01, 3000, 2900, 3200)
        # ETH hits take profit, BTC stays open
        triggered = self.engine.check_stop_take_profit({"BTC_USDT": 50500, "ETH_USDT": 3300})
        assert len(triggered) == 1
        assert triggered[0]["symbol"] == "ETH_USDT"
