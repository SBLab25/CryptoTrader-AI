from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
async def phase3_db():
    import os

    from src.core.config import settings
    from src.db.database import close_db, init_db

    original = settings.database_url
    db_path = "phase3-test.sqlite3"
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
        if os.path.exists(db_path):
            os.remove(db_path)


class TestReducers:
    def test_append_errors(self):
        from src.agents.graph.state import _append_errors

        assert _append_errors(["a"], ["b"]) == ["a", "b"]

    def test_keep_last(self):
        from src.agents.graph.state import _keep_last

        assert _keep_last("old", "new") == "new"


class TestRoutingFunctions:
    def test_route_after_market_analyst(self):
        from langgraph.graph import END
        from src.agents.graph.orchestrator_graph import _route_after_market_analyst

        assert _route_after_market_analyst({"ohlcv": [], "indicators": {}}) == END
        assert _route_after_market_analyst({"ohlcv": [1], "indicators": {"rsi": 1}}) == "signal_agent"

    def test_route_after_signal_agent(self):
        from langgraph.graph import END
        from src.agents.graph.orchestrator_graph import _route_after_signal_agent

        assert _route_after_signal_agent({"signal": {"action": "HOLD"}}) == END
        assert _route_after_signal_agent({"signal": {"action": "BUY"}}) == "risk_engine"


class TestSignalStrategySelection:
    def test_select_strategy(self):
        from src.agents.graph.nodes.signal_agent import _select_strategy

        assert _select_strategy({"rsi": 28, "bb_percent_b": 0.1}) == "mean_reversion"
        assert _select_strategy({"rsi": 50, "bb_percent_b": 0.5, "volume_ratio": 2.0}) == "breakout"
        assert _select_strategy({"rsi": 50, "bb_percent_b": 0.5, "ema_trend": "bullish", "macd_histogram": 0.05}) == "momentum"


class TestApprovalGate:
    @pytest.mark.asyncio
    async def test_paper_mode_auto_approves(self):
        from src.agents.graph.nodes.approval_gate import approval_gate_node

        result = await approval_gate_node(
            {
                "mode": "paper",
                "symbol": "BTC_USDT",
                "signal": {"action": "BUY", "confidence": 0.8},
                "risk_result": {"approved_position_usd": 500.0},
            }
        )
        assert result["approval_granted"] is True
        assert result["approval_status"] == "APPROVED"


class TestExecutionNode:
    @pytest.mark.asyncio
    async def test_skips_when_approval_denied(self):
        from src.agents.graph.nodes.execution_agent import execution_agent_node

        result = await execution_agent_node({"approval_granted": False})
        assert result["execution_result"]["status"] == "skipped"


class TestApprovalRoutes:
    @pytest.mark.asyncio
    async def test_approval_round_trip(self, phase3_db):
        from src.api.auth.jwt import create_access_token
        from src.core.server import create_app
        from src.db.database import get_db_session
        from src.db.models import ApprovalRequestRecord

        async with get_db_session() as session:
            record = ApprovalRequestRecord(
                symbol="BTC_USDT",
                side="buy",
                position_usd=250.0,
                confidence=0.8,
                status="PENDING",
                trade_payload_json="{}",
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(minutes=5),
            )
            session.add(record)
            await session.commit()
            approval_id = record.id

        token = create_access_token("alice")
        headers = {"Authorization": f"Bearer {token}"}
        with TestClient(create_app(start_background=False)) as client:
            pending = client.get("/api/approvals/pending", headers=headers)
            assert pending.status_code == 200
            assert pending.json()[0]["id"] == approval_id

            decision = client.post(f"/api/approvals/{approval_id}/approve", headers=headers)
            assert decision.status_code == 200
            assert decision.json()["status"] == "approved"

            detail = client.get(f"/api/approvals/{approval_id}", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["status"] == "APPROVED"


class TestGraphBuild:
    def test_graph_compiles(self):
        from src.agents.graph.orchestrator_graph import build_trading_graph

        graph = build_trading_graph(checkpointer=None)
        assert graph.entry_point == "market_analyst"

    @pytest.mark.asyncio
    async def test_market_node_handles_errors(self):
        from src.agents.graph.nodes.market_analyst import market_analyst_node

        with patch("src.agents.graph.nodes.market_analyst._read_from_timescale", AsyncMock(side_effect=Exception("boom"))):
            result = await market_analyst_node({"symbol": "BTC_USDT"})
        assert result["errors"]
