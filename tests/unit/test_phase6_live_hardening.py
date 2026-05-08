from __future__ import annotations

import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_default_state_is_closed(self, mock_redis):
        with patch("src.utils.circuit_breaker.get_redis", return_value=mock_redis):
            from src.utils.circuit_breaker import CircuitBreaker

            assert await CircuitBreaker("cryptocom").get_state() == CircuitBreaker.STATE_CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self, mock_redis):
        mock_redis.incr = AsyncMock(return_value=5)
        with patch("src.utils.circuit_breaker.get_redis", return_value=mock_redis), patch(
            "src.utils.circuit_breaker.CircuitBreaker._notify_open", AsyncMock()
        ):
            from src.utils.circuit_breaker import CircuitBreaker

            await CircuitBreaker("cryptocom").record_failure()

        set_calls = [str(call) for call in mock_redis.set.call_args_list]
        assert any("OPEN" in call for call in set_calls)

    @pytest.mark.asyncio
    async def test_open_raises_until_timeout_expires(self, mock_redis):
        mock_redis.get = AsyncMock(
            side_effect=lambda key: "OPEN" if "state" in key else str(time.time() - 1)
        )
        with patch("src.utils.circuit_breaker.get_redis", return_value=mock_redis), patch(
            "src.utils.circuit_breaker.OPEN_TIMEOUT_S", 3600
        ):
            from src.utils.circuit_breaker import CircuitBreaker, CircuitOpenError

            with pytest.raises(CircuitOpenError):
                async with CircuitBreaker("cryptocom"):
                    pass

    @pytest.mark.asyncio
    async def test_success_from_half_open_recovers(self, mock_redis):
        mock_redis.get = AsyncMock(return_value="HALF_OPEN")
        with patch("src.utils.circuit_breaker.get_redis", return_value=mock_redis), patch(
            "src.utils.circuit_breaker.CircuitBreaker._notify_recovery", AsyncMock()
        ) as notify:
            from src.utils.circuit_breaker import CircuitBreaker

            await CircuitBreaker("cryptocom").record_success()

        assert notify.await_count == 1


class TestNtfyNotifications:
    @pytest.fixture
    def ntfy_settings(self):
        settings = MagicMock()
        settings.ntfy_url = "http://localhost:8080"
        settings.ntfy_topic = "cryptotrader"
        settings.ntfy_token = "secret"
        return settings

    @pytest.mark.asyncio
    async def test_send_notification_success(self, ntfy_settings):
        response = MagicMock(status_code=200)
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=response)

        with patch("src.notifications.ntfy.settings", ntfy_settings), patch(
            "httpx.AsyncClient", return_value=client
        ):
            from src.notifications.ntfy import send_notification

            assert await send_notification("Test", "Body", priority=5) is True
            headers = client.post.call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer secret"
            assert headers["Priority"] == "5"

    @pytest.mark.asyncio
    async def test_skip_when_not_configured(self):
        settings = MagicMock(ntfy_url="", ntfy_topic="", ntfy_token="")
        with patch("src.notifications.ntfy.settings", settings):
            from src.notifications.ntfy import send_notification

            assert await send_notification("Test", "Body") is False

    @pytest.mark.asyncio
    async def test_trade_opened_formats_body(self, ntfy_settings):
        with patch("src.notifications.ntfy.settings", ntfy_settings), patch(
            "src.notifications.ntfy.send_notification", AsyncMock()
        ) as send:
            from src.notifications.ntfy import notify_trade_opened

            await notify_trade_opened("BTC_USDT", "BUY", 67300.0, 65000.0, 70000.0, 0.78, 200.0, "momentum")

        message = send.await_args.kwargs["message"]
        assert "65000" in message
        assert "70000" in message


class TestLiveEngine:
    @pytest.fixture
    def fake_ccxt_module(self):
        ccxt_pkg = types.ModuleType("ccxt")
        ccxt_async = types.ModuleType("ccxt.async_support")
        exchange = MagicMock()
        exchange.fetch_accounts = AsyncMock(return_value=[])
        exchange.fetch_ticker = AsyncMock(return_value={"last": 67000})
        exchange.fetch_balance = AsyncMock(return_value={"USDT": {"free": 1000}})
        exchange.create_order = AsyncMock(return_value={"id": "abc", "amount": 0.01, "price": 67000})
        ccxt_async.cryptocom = MagicMock(return_value=exchange)
        ccxt_pkg.async_support = ccxt_async
        return ccxt_pkg, ccxt_async, exchange

    @pytest.mark.asyncio
    async def test_refuses_when_sandbox_enabled(self):
        vault = MagicMock()
        settings = MagicMock(cryptocom_sandbox=True, vault_addr="", vault_token="")
        with patch("src.exchange.live_engine.settings", settings):
            from src.exchange.live_engine import LiveEngine

            with pytest.raises(RuntimeError, match="CRYPTOCOM_SANDBOX=True"):
                await LiveEngine(vault=vault).initialise()

    @pytest.mark.asyncio
    async def test_clears_keys_on_del(self):
        from src.exchange.live_engine import LiveEngine

        engine = LiveEngine(vault=MagicMock())
        engine._exchange = MagicMock(apiKey="key", secret="secret")
        engine.__del__()
        assert engine._exchange.apiKey is None
        assert engine._exchange.secret is None

    @pytest.mark.asyncio
    async def test_place_order_uses_circuit_breaker_and_returns_order(self, fake_ccxt_module):
        ccxt_pkg, ccxt_async, exchange = fake_ccxt_module
        vault = MagicMock()
        vault.get = MagicMock(side_effect=lambda key: {"exchange_api_key": "k", "exchange_api_secret": "s"}[key])
        settings = MagicMock(cryptocom_sandbox=False, vault_addr="", vault_token="")

        with patch.dict(sys.modules, {"ccxt": ccxt_pkg, "ccxt.async_support": ccxt_async}), patch(
            "src.exchange.live_engine.settings", settings
        ), patch("src.exchange.live_engine.CircuitBreaker", autospec=True) as cb_cls, patch(
            "src.exchange.live_engine.LiveEngine._audit_order", AsyncMock()
        ), patch("src.exchange.live_engine.LiveEngine._notify_order", AsyncMock()):
            cb_cls.return_value.__aenter__ = AsyncMock(return_value=cb_cls.return_value)
            cb_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            from src.exchange.live_engine import LiveEngine

            order = await LiveEngine(vault=vault).place_order("BTC_USDT", "BUY", size_pct=0.02)

        assert order["id"] == "abc"
        assert exchange.create_order.await_count == 1


class TestPreflightChecker:
    def test_check_result_icons(self):
        from scripts.preflight_check import CheckResult

        assert CheckResult("x", "PASS").icon == "OK"
        assert CheckResult("x", "WARN").icon == "WARN"
        assert CheckResult("x", "FAIL").icon == "FAIL"

    def test_jwt_check_passes_with_long_key(self):
        from scripts.preflight_check import PreflightChecker

        checker = PreflightChecker()
        settings = MagicMock(jwt_signing_key="a" * 32)
        with patch("scripts.preflight_check.get_settings", return_value=settings):
            checker.check_jwt()
        assert all(item.status == "PASS" for item in checker.results)

    def test_settings_check_warns_on_large_position_size(self):
        from scripts.preflight_check import PreflightChecker

        checker = PreflightChecker()
        settings = MagicMock(
            approval_threshold_usd=100.0,
            approval_timeout_seconds=300,
            max_position_size_pct=10.0,
            max_daily_loss_pct=5.0,
        )
        with patch("scripts.preflight_check.get_settings", return_value=settings):
            checker.check_settings()

        position_result = next(item for item in checker.results if "Max position size" in item.name)
        assert position_result.status == "WARN"

    @pytest.mark.asyncio
    async def test_run_returns_bool(self):
        from scripts.preflight_check import PreflightChecker

        checker = PreflightChecker()
        with patch.object(checker, "check_vault", AsyncMock()), patch.object(
            checker, "check_database", AsyncMock()
        ), patch.object(checker, "check_redis", AsyncMock()), patch.object(
            checker, "check_exchange", AsyncMock()
        ), patch.object(checker, "check_notifications", AsyncMock()), patch.object(
            checker, "check_paper_history", AsyncMock()
        ), patch.object(checker, "check_qdrant", MagicMock()), patch.object(
            checker, "check_jwt", MagicMock()
        ), patch.object(checker, "check_settings", MagicMock()):
            result = await checker.run()

        assert isinstance(result, bool)
