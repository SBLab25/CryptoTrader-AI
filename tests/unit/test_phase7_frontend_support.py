import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
async def phase7_db():
    from src.core.config import settings
    from src.db.database import close_db, init_db

    original = settings.database_url
    db_path = "phase7-test.sqlite3"
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


async def _seed_user(username: str = "admin", password: str = "secret123"):
    from src.db.database import get_db_session
    from src.db.user_repository import UserRepository

    async with get_db_session() as session:
        repo = UserRepository(session)
        await repo.create(username, password)


class TestPhase7AuthCookies:
    @pytest.mark.asyncio
    async def test_login_sets_auth_cookies_and_cookie_auth_works(self, phase7_db):
        from src.core.server import create_app

        await _seed_user()

        with TestClient(create_app(start_background=False)) as client:
            response = client.post("/auth/token", data={"username": "admin", "password": "secret123"})
            assert response.status_code == 200
            assert response.cookies.get("access_token")
            assert response.cookies.get("refresh_token")

            me = client.get("/auth/me")
            assert me.status_code == 200
            assert me.json()["username"] == "admin"

    @pytest.mark.asyncio
    async def test_refresh_accepts_cookie_without_body(self, phase7_db):
        from src.core.server import create_app

        await _seed_user()

        with TestClient(create_app(start_background=False)) as client:
            login = client.post("/auth/token", data={"username": "admin", "password": "secret123"})
            assert login.status_code == 200

            refreshed = client.post("/auth/refresh")
            assert refreshed.status_code == 200
            assert refreshed.cookies.get("access_token")

    @pytest.mark.asyncio
    async def test_ws_token_endpoint_requires_existing_auth(self, phase7_db):
        from src.core.server import create_app

        await _seed_user()

        with TestClient(create_app(start_background=False)) as client:
            client.post("/auth/token", data={"username": "admin", "password": "secret123"})
            response = client.get("/auth/ws-token")
            assert response.status_code == 200
            assert "token" in response.json()


class TestPhase7DashboardRoutes:
    @pytest.mark.asyncio
    async def test_ohlcv_route_falls_back_to_market_analyst(self, phase7_db):
        from src.core.server import create_app

        await _seed_user()

        fake_ohlcv = [
            {"timestamp": 1710000000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 12},
            {"timestamp": 1710003600, "open": 1.5, "high": 2.1, "low": 1.2, "close": 2.0, "volume": 15},
        ]

        with TestClient(create_app(start_background=False)) as client, patch(
            "src.core.server.orchestrator.market_analyst.fetch_ohlcv",
            AsyncMock(return_value=fake_ohlcv),
        ):
            client.post("/auth/token", data={"username": "admin", "password": "secret123"})
            response = client.get("/api/ohlcv?symbol=BTC_USDT&timeframe=1h&limit=2")
            assert response.status_code == 200
            assert response.json()[0]["time"] == 1710000000

    @pytest.mark.asyncio
    async def test_training_routes_report_state(self, phase7_db):
        from src.core.server import create_app

        await _seed_user()

        with TestClient(create_app(start_background=False)) as client:
            client.post("/auth/token", data={"username": "admin", "password": "secret123"})
            started = client.post("/api/training/start", json={"symbol": "BTC_USDT", "timesteps": 200000, "speed_multiplier": 50})
            assert started.status_code == 200

            status = client.get("/api/training/status")
            assert status.status_code == 200
            assert status.json()["running"] is True
            assert status.json()["symbol"] == "BTC_USDT"

            stopped = client.post("/api/training/stop")
            assert stopped.status_code == 200
            assert stopped.json()["status"] == "stopped"

    def test_health_detail_alias_returns_full_payload(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.get("/health/detail")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
