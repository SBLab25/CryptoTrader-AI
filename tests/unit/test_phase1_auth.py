import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


class TestCreateAccessToken:
    def test_creates_valid_jwt(self):
        from src.api.auth.jwt import create_access_token, decode_token

        token = create_access_token("alice")
        payload = decode_token(token, expected_type="access")
        assert payload.username == "alice"
        assert payload.token_type == "access"

    def test_refresh_token_type(self):
        from src.api.auth.jwt import create_refresh_token, decode_token

        token = create_refresh_token("alice")
        payload = decode_token(token, expected_type="refresh")
        assert payload.username == "alice"
        assert payload.token_type == "refresh"


class TestDecodeToken:
    def test_wrong_type_raises_401(self):
        from src.api.auth.jwt import create_access_token, decode_token

        token = create_access_token("bob")
        with pytest.raises(HTTPException) as exc:
            decode_token(token, expected_type="refresh")
        assert exc.value.status_code == 401

    def test_empty_token_raises_401(self):
        from src.api.auth.jwt import decode_token

        with pytest.raises(HTTPException) as exc:
            decode_token("")
        assert exc.value.status_code == 401


class TestScrubSecrets:
    def test_scrubs_api_key(self):
        from src.api.middleware.audit_logger import _scrub_secrets

        result = _scrub_secrets({"api_key": "sk-real-key"})
        assert result["api_key"] == "[REDACTED]"

    def test_scrubs_nested(self):
        from src.api.middleware.audit_logger import _scrub_secrets

        result = _scrub_secrets({"config": {"api_secret": "real-secret", "mode": "live"}})
        assert result["config"]["api_secret"] == "[REDACTED]"
        assert result["config"]["mode"] == "live"


class TestUserModel:
    def test_password_is_hashed(self):
        from src.db.models import User

        user = User.create(username="alice", password="my-plain-password")
        assert user.password_hash != "my-plain-password"
        assert user.password_hash.startswith("$2b$")

    def test_correct_password_verifies(self):
        from src.db.models import User

        user = User.create(username="alice", password="correct-password")
        assert user.verify_password("correct-password") is True


class TestProtectedEndpoints:
    def test_health_returns_200(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_trading_start_requires_auth(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.post("/api/trading/start")
        assert response.status_code == 401

    def test_portfolio_requires_auth(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.get("/api/portfolio")
        assert response.status_code == 401

    def test_backtest_requires_auth(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.post("/api/backtest")
        assert response.status_code == 401

    def test_llm_switch_requires_auth(self):
        from src.core.server import create_app

        with TestClient(create_app(start_background=False)) as client:
            response = client.post("/api/llm/switch")
        assert response.status_code == 401
