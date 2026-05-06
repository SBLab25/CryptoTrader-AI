from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestEmbeddingBuilders:
    def test_format_indicators(self):
        from src.memory.embeddings import _format_indicators

        text = _format_indicators({"rsi": 32.5, "macd_histogram": 0.05, "bb_percent_b": 0.1, "ema_trend": "bullish", "volume_ratio": 2.0})
        assert "RSI 32.5" in text
        assert "positive" in text
        assert "lower Bollinger" in text
        assert "bullish" in text
        assert "high volume" in text

    def test_build_signal_text_truncates(self):
        from src.memory.embeddings import MAX_TEXT_LENGTH, _build_signal_text

        text = _build_signal_text("x" * 10000, {}, "BTC_USDT", "BUY", "momentum")
        assert len(text) <= MAX_TEXT_LENGTH * 4


class TestSignalStore:
    @pytest.mark.asyncio
    async def test_store_signal_calls_upsert(self):
        mock_qdrant = MagicMock()
        mock_qdrant.upsert = MagicMock()
        with patch("src.memory.signal_store.get_qdrant_client", return_value=mock_qdrant), patch(
            "src.memory.signal_store.embed_signal", return_value=[0.1] * 1024
        ), patch("src.memory.signal_store._mark_stored_in_db", AsyncMock()):
            from src.memory.signal_store import store_signal

            result = await store_signal(
                signal_id="signal-1",
                symbol="BTC_USDT",
                action="BUY",
                confidence=0.8,
                strategy="momentum",
                reasoning="RSI oversold",
                indicators={"rsi": 32.0},
            )
        assert result is True
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_outcome_calls_set_payload(self):
        mock_qdrant = MagicMock()
        mock_qdrant.set_payload = MagicMock()
        with patch("src.memory.signal_store.get_qdrant_client", return_value=mock_qdrant):
            from src.memory.signal_store import update_outcome

            result = await update_outcome("signal-1", "WIN", 2.3, "trade-1")
        assert result is True
        mock_qdrant.set_payload.assert_called_once()


class TestRetriever:
    @pytest.mark.asyncio
    async def test_returns_empty_when_unavailable(self):
        with patch("src.memory.retriever.is_qdrant_available", return_value=False):
            from src.memory.retriever import retrieve_similar_signals

            assert await retrieve_similar_signals({"rsi": 30}, "BTC_USDT") == []

    def test_format_rag_context(self):
        from src.memory.retriever import format_rag_context

        text = format_rag_context(
            [
                {
                    "action": "BUY",
                    "outcome": "WIN",
                    "pnl_pct": 2.3,
                    "confidence": 0.78,
                    "rsi": 32.1,
                    "ema_trend": "bullish",
                    "created_at": "2024-03-15T14:30:00Z",
                    "score": 0.92,
                }
            ]
        )
        assert "Historical analogues" in text
        assert "WIN" in text
        assert "+2.3%" in text


class TestCorrelationGraph:
    @pytest.mark.asyncio
    async def test_builds_edge_for_correlated_pairs(self):
        async def mock_fetch(symbol, _points):
            return [float(i) for i in range(30)] if "BTC" in symbol else [float(i) * 1.05 for i in range(30)]

        with patch("src.graph_analysis.correlation._fetch_prices", mock_fetch):
            from src.graph_analysis.correlation import build_correlation_graph

            graph = await build_correlation_graph(["BTC_USDT", "ETH_USDT"])
        assert graph.has_edge("BTC_USDT", "ETH_USDT")

    @pytest.mark.asyncio
    async def test_cache_round_trip(self):
        from src.graph_analysis.correlation import SimpleGraph, load_graph_from_cache, save_graph_to_cache

        graph = SimpleGraph()
        graph.add_edge("BTC_USDT", "ETH_USDT", weight=0.85)
        stored = {}
        mock_redis = AsyncMock()

        async def mock_set(key, value, ex=None):
            stored[key] = value

        async def mock_get(key):
            return stored.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get
        with patch("src.db.redis_client.get_redis", return_value=mock_redis):
            await save_graph_to_cache(graph)
            loaded = await load_graph_from_cache()
        assert loaded is not None
        assert loaded.has_edge("BTC_USDT", "ETH_USDT")


class TestAnalyticsRoutes:
    def test_memory_info_requires_auth(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.get("/api/analytics/memory/info")
        assert response.status_code == 401

    def test_memory_info_returns_payload(self):
        from src.api.auth.jwt import create_access_token
        from src.core.server import create_app

        token = create_access_token("alice")
        headers = {"Authorization": f"Bearer {token}"}
        with TestClient(create_app(start_background=False)) as client:
            response = client.get("/api/analytics/memory/info", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert "qdrant" in body
        assert "embeddings" in body
