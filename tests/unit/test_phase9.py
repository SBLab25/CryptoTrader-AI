from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shutdown import ShutdownHandler
from src.exchange.permission_check import PermissionCheckResult
from src.notifications.ntfy import NtfyClient
from src.risk.hard_caps import HardCaps
from src.stability.graduation_checker import CriterionResult, GraduationReport
from src.stability.outcome_feedback import OutcomeFeedback
from src.stability.parameter_sweep import FAST_GRID, ParameterSweep, StrategyParams, _atr, _backtest, _ema, _rsi
from src.stability.stability_monitor import StabilityMonitor, StabilityReport, StabilityIssue


class TestParameterSweep:
    def _make_trend_up(self, n=200):
        import random

        closes = [100.0 + i * 0.3 + random.gauss(0, 0.5) for i in range(n)]
        highs = [close + abs(random.gauss(0, 0.5)) for close in closes]
        lows = [close - abs(random.gauss(0, 0.5)) for close in closes]
        return closes, highs, lows

    def _make_params(self, **kwargs) -> StrategyParams:
        defaults = dict(
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            ema_fast=20,
            ema_slow=50,
            confidence_floor=0.55,
            position_size_pct=0.03,
            atr_sl_multiplier=1.5,
            atr_tp_multiplier=3.0,
        )
        defaults.update(kwargs)
        return StrategyParams(**defaults)

    def test_backtest_returns_result(self):
        closes, highs, lows = self._make_trend_up()
        result = _backtest(closes, highs, lows, self._make_params())
        assert result is not None
        assert 0.0 <= result.win_rate <= 1.0
        assert result.max_drawdown >= 0.0
        assert result.total_trades >= 0

    def test_backtest_short_series_returns_invalid(self):
        closes = [100.0] * 10
        highs = [value + 1 for value in closes]
        lows = [value - 1 for value in closes]
        result = _backtest(closes, highs, lows, self._make_params())
        assert result.sharpe == -99.0

    def test_ema_returns_correct_length(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert len(_ema(prices, period=3)) == len(prices)

    def test_rsi_values_bounded(self):
        prices = [100.0 + i * 0.5 for i in range(30)]
        result = _rsi(prices)
        assert all(value >= 0 for value in result)
        assert all(value <= 100 for value in result)

    def test_atr_positive_values(self):
        n = 50
        closes = [100.0 + i * 0.1 for i in range(n)]
        highs = [value + 1.0 for value in closes]
        lows = [value - 1.0 for value in closes]
        result = _atr(highs, lows, closes)
        assert len(result) == n
        assert result[15] > 0

    @pytest.mark.asyncio
    async def test_sweep_runs_without_ts_store(self):
        sweep = ParameterSweep(ts_store=None)
        results = await sweep.run(symbol="BTC_USDT", lookback_days=30, fast=True)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_sweep_results_sorted_by_sharpe(self):
        sweep = ParameterSweep(ts_store=None)
        results = await sweep.run(symbol="BTC_USDT", lookback_days=30, fast=True)
        if len(results) >= 2:
            assert all(results[i].sharpe >= results[i + 1].sharpe for i in range(len(results) - 1))

    def test_params_to_dict_round_trip(self):
        params = self._make_params(rsi_period=10, confidence_floor=0.60)
        payload = params.to_dict()
        assert payload["rsi_period"] == 10
        assert payload["confidence_floor"] == 0.60

    def test_fast_grid_present(self):
        assert "rsi_period" in FAST_GRID


class TestHardCaps:
    def _make_caps(self, single=100.0, daily=200.0) -> HardCaps:
        caps = HardCaps()
        caps._max_single = single
        caps._max_daily = daily
        caps._loaded = True
        return caps

    def test_trade_within_caps_approved(self):
        result = self._make_caps().check(usd_amount=50, daily_loss_usd=0)
        assert result.approved is True
        assert result.cap_hit is None

    def test_trade_exceeds_single_cap(self):
        result = self._make_caps(single=25, daily=50).check(usd_amount=30)
        assert result.approved is False
        assert result.cap_hit == "single_trade"

    def test_daily_loss_at_cap_rejects(self):
        result = self._make_caps(single=100, daily=50).check(usd_amount=10, daily_loss_usd=50)
        assert result.approved is False
        assert result.cap_hit == "daily_loss"

    def test_load_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_SINGLE_TRADE_USD", "75")
        monkeypatch.setenv("MAX_DAILY_LOSS_USD", "150")
        caps = HardCaps()
        caps.load_from_env()
        assert caps.max_single_trade_usd == 75.0
        assert caps.max_daily_loss_usd == 150.0

    @pytest.mark.asyncio
    async def test_load_from_vault_raises_without_caps(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "live")
        monkeypatch.delenv("MAX_SINGLE_TRADE_USD", raising=False)
        monkeypatch.delenv("MAX_DAILY_LOSS_USD", raising=False)
        mock_vault = AsyncMock()
        mock_vault.get = AsyncMock(return_value="")
        caps = HardCaps()
        with pytest.raises(RuntimeError):
            await caps.load_from_vault(mock_vault)


class TestOutcomeFeedback:
    @pytest.mark.asyncio
    async def test_record_outcome_calls_signal_memory(self):
        memory = AsyncMock()
        memory.update_outcome = AsyncMock()
        feedback = OutcomeFeedback(signal_memory=memory)
        await feedback.record_trade_outcome("signal-123", "BTC_USDT", 42.5, 0.043, 2.5, "take_profit")
        memory.update_outcome.assert_called_once_with(signal_id="signal-123", pnl=42.5, pnl_pct=0.043)

    @pytest.mark.asyncio
    async def test_record_outcome_no_memory_does_not_raise(self):
        feedback = OutcomeFeedback(signal_memory=None)
        await feedback.record_trade_outcome("x", "BTC_USDT", -10.0, -0.01, 1.0, "stop_loss")

    @pytest.mark.asyncio
    async def test_get_feedback_stats_with_memory(self):
        memory = AsyncMock()
        memory.collection_stats = AsyncMock(return_value={"vectors_count": 150, "indexed_vectors_count": 150, "status": "green"})
        stats = await OutcomeFeedback(signal_memory=memory).get_feedback_stats()
        assert stats["available"] is True
        assert stats["vectors_total"] == 150


class TestGraduationChecker:
    def test_report_all_passed_when_no_issues(self):
        results = [
            CriterionResult("win_rate", "Win Rate >= 50%", True, 0.55, ">= 50%", "55%"),
            CriterionResult("profit_factor", "Profit Factor >= 1.3", True, 1.4, ">= 1.3", "1.4"),
        ]
        report = GraduationReport(timestamp=datetime.now(timezone.utc), all_passed=True, performance=results, stability=[])
        assert report.all_passed is True

    def test_summary_lines_not_empty(self):
        report = GraduationReport(
            timestamp=datetime.now(timezone.utc),
            all_passed=False,
            performance=[CriterionResult("win_rate", "Win Rate", False, 0.45, ">=50%", "45%")],
            stability=[],
        )
        lines = report.summary_lines()
        assert lines
        assert any("GRADUATION" in line for line in lines)


class TestShutdownHandler:
    @pytest.mark.asyncio
    async def test_shutdown_requested_initially_false(self):
        assert ShutdownHandler().shutdown_requested is False

    @pytest.mark.asyncio
    async def test_shutdown_stops_consumer(self):
        consumer = AsyncMock()
        consumer.stop = AsyncMock()
        await ShutdownHandler(redis_consumer=consumer).shutdown()
        consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_approval_queue(self):
        approvals = AsyncMock()
        approvals.expire_all_pending = AsyncMock(return_value=2)
        await ShutdownHandler(approval_queue=approvals).shutdown()
        approvals.expire_all_pending.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_notifies_ws_clients(self):
        broadcaster = AsyncMock()
        broadcaster.emit = AsyncMock()
        await ShutdownHandler(broadcaster=broadcaster).shutdown()
        broadcaster.emit.assert_called_once()
        assert broadcaster.emit.call_args[0][0] == "system"

    @pytest.mark.asyncio
    async def test_shutdown_writes_audit_event(self):
        audit = AsyncMock()
        audit.log = AsyncMock()
        await ShutdownHandler(audit=audit).shutdown()
        audit.log.assert_called_once()
        assert audit.log.call_args[0][0].event_type == "SYSTEM_SHUTDOWN"

    @pytest.mark.asyncio
    async def test_shutdown_drains_graph_task(self):
        async def fast_task():
            await asyncio.sleep(0.01)

        task = asyncio.create_task(fast_task())
        await ShutdownHandler(graph_task=task).shutdown()
        assert task.done()


class TestNtfyClient:
    def _make_client(self) -> NtfyClient:
        return NtfyClient(base_url="http://localhost:8080", topic="test", token="test-token")

    @pytest.mark.asyncio
    async def test_send_returns_bool(self):
        client = self._make_client()
        with patch("aiohttp.ClientSession") as session_cls:
            response = AsyncMock()
            response.status = 200
            session = session_cls.return_value
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=False)
            session.post.return_value.__aenter__ = AsyncMock(return_value=response)
            session.post.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.send("Title", "Message")
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_send_returns_false_on_connection_error(self):
        client = self._make_client()
        with patch("aiohttp.ClientSession", side_effect=Exception("conn refused")):
            result = await client.send("Test", "Message")
            assert result is False

    @pytest.mark.asyncio
    async def test_trade_opened_calls_send(self):
        client = self._make_client()
        client.send = AsyncMock(return_value=True)
        await client.trade_opened("BTC_USDT", "buy", 500, 65000, mode="paper")
        client.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_uses_max_priority(self):
        client = self._make_client()
        client.send = AsyncMock(return_value=True)
        await client.circuit_breaker_open("cryptocom")
        assert client.send.call_args[1]["priority"] == 5


class TestStabilityMonitor:
    @pytest.mark.asyncio
    async def test_run_without_db_returns_healthy(self):
        report = await StabilityMonitor(db_pool=None, redis_client=None).run_hourly_check()
        assert isinstance(report, StabilityReport)
        assert report.is_healthy

    @pytest.mark.asyncio
    async def test_redis_lag_above_threshold_creates_issue(self):
        redis = AsyncMock()
        redis.xinfo_groups = AsyncMock(return_value=[{"lag": 2000}])
        issue = await StabilityMonitor(redis_client=redis)._check_redis_stream_health()
        assert issue is not None
        assert issue.severity == "warning"

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_creates_warning(self):
        db = AsyncMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"cnt": 5})
        db.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
        memory = AsyncMock()
        memory.collection_stats = AsyncMock(return_value={"available": False})
        issue = await StabilityMonitor(db_pool=db, signal_memory=memory)._check_qdrant_outcome_lag()
        assert issue is not None
        assert "qdrant" in issue.name

    def test_report_has_critical_true_when_critical_issue(self):
        report = StabilityReport(timestamp=datetime.now(timezone.utc), issues=[StabilityIssue("critical", "orphaned_positions", "3 positions with no SL/TP")])
        assert report.has_critical is True
        assert report.is_healthy is False


class TestPermissionCheckResult:
    def test_report_object_shape(self):
        result = PermissionCheckResult(passed=False, error="boom")
        assert result.passed is False
        assert result.error == "boom"
