from unittest.mock import AsyncMock, patch

import pytest


class TestWebSocketFeedNormalization:
    def test_normalize_converts_slash_to_underscore(self):
        from src.exchange.websocket_feed import WebSocketFeed

        tick = WebSocketFeed._normalize("BTC/USDT", [1700000000000, 1, 2, 0.5, 1.5, 10])
        assert tick["symbol"] == "BTC_USDT"

    def test_normalize_all_fields_present(self):
        from src.exchange.websocket_feed import WebSocketFeed

        tick = WebSocketFeed._normalize("ETH/USDT", [1700000000000, 1, 2, 0.5, 1.5, 10])
        for key in ("symbol", "timestamp", "open", "high", "low", "close", "volume", "source"):
            assert key in tick


class TestRedisClientUnit:
    @pytest.mark.asyncio
    async def test_publish_tick_calls_xadd(self):
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value="1-0")
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch("src.db.redis_client.get_redis", return_value=mock_redis):
            from src.db.redis_client import publish_tick

            await publish_tick(
                {
                    "symbol": "BTC_USDT",
                    "timestamp": 1700000000000,
                    "open": 67100.0,
                    "high": 67500.0,
                    "low": 67050.0,
                    "close": 67300.0,
                    "volume": 15.2,
                }
            )

        mock_redis.xadd.assert_called_once()
        assert mock_redis.xadd.call_args[0][0] == "market:ticks"

    @pytest.mark.asyncio
    async def test_broadcast_publishes_json(self):
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        with patch("src.db.redis_client.get_redis", return_value=mock_redis):
            from src.db.redis_client import broadcast

            await broadcast({"type": "portfolio_update", "value": 42})

        mock_redis.publish.assert_called_once()
        assert mock_redis.publish.call_args[0][0] == "ws:broadcast"


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=5)
        mock_redis.expire = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch("src.db.redis_client.get_redis", return_value=mock_redis):
            from src.db.redis_client import CB_OPEN, cb_record_failure

            state = await cb_record_failure("cryptocom")

        assert state == CB_OPEN

    @pytest.mark.asyncio
    async def test_success_resets_to_closed(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch("src.db.redis_client.get_redis", return_value=mock_redis):
            from src.db.redis_client import cb_record_success

            await cb_record_success("cryptocom")

        mock_redis.delete.assert_called_once()
        mock_redis.set.assert_called_once()


@pytest.fixture
async def phase2_db():
    import os

    from src.core.config import settings
    from src.db.database import close_db, init_db

    original = settings.database_url
    db_path = "phase2-test.sqlite3"
    if os.path.exists(db_path):
        os.remove(db_path)
    settings.database_url = f"sqlite:///./{db_path}"
    await close_db()
    await init_db()
    try:
        yield db_path
    finally:
        await close_db()
        settings.database_url = original


class TestSignalLogAndCredentials:
    @pytest.mark.asyncio
    async def test_signal_log_insert_and_read(self, phase2_db):
        from src.db.database import get_db_session
        from src.db.timescale import SignalLogStore

        async with get_db_session() as session:
            signal_id = await SignalLogStore.insert(
                session,
                {
                    "symbol": "BTC_USDT",
                    "action": "buy",
                    "confidence": 0.78,
                    "reasoning": "RSI oversold with bullish momentum",
                    "llm_provider": "anthropic",
                    "risk_passed": False,
                },
            )

        async with get_db_session() as session:
            recent = await SignalLogStore.get_recent(session, symbol="BTC_USDT", limit=1)

        assert signal_id
        assert recent[0]["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_credential_store_round_trip(self, phase2_db):
        from src.db.database import get_db_session
        from src.db.timescale import CredentialStore

        async with get_db_session() as session:
            cred_id = await CredentialStore.save(
                session,
                exchange="cryptocom",
                api_key="key-123",
                api_secret="secret-456",
                vault_key="vault-test-key",
            )

        async with get_db_session() as session:
            record = await CredentialStore.load(session, "cryptocom", "vault-test-key")

        assert cred_id
        assert record["api_key"] == "key-123"
        assert record["api_secret"] == "secret-456"
