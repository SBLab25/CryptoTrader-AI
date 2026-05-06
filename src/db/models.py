"""Additional ORM models introduced by Phase 1."""

from datetime import datetime
from uuid import uuid4

from passlib.context import CryptContext
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, LargeBinary, String, Text

from src.db.database import Base

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def set_password(self, plain_password: str) -> None:
        self.password_hash = _pwd_context.hash(plain_password)

    def verify_password(self, plain_password: str) -> bool:
        return _pwd_context.verify(plain_password, self.password_hash)

    @classmethod
    def create(cls, username: str, password: str) -> "User":
        user = cls(username=username)
        user.set_password(password)
        return user


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(36), nullable=True)
    entity_type = Column(String(50), nullable=True)
    actor = Column(String(100), nullable=False, default="system")
    details_json = Column(Text, nullable=False, default="{}")
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class OHLCVRecord(Base):
    __tablename__ = "ohlcv"

    timestamp = Column(DateTime, primary_key=True)
    symbol = Column(String(20), primary_key=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    source = Column(String(20), nullable=False, default="rest")


class SignalLogRecord(Base):
    __tablename__ = "signal_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String(20), nullable=False, index=True)
    strategy = Column(String(50), nullable=False, default="ai_llm_ta")
    action = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    entry_price = Column(Float, nullable=True)
    rsi = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)
    bb_percent_b = Column(Float, nullable=True)
    ema_trend = Column(String(20), nullable=True)
    atr = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    risk_passed = Column(Boolean, nullable=True, default=None)
    rejection_reason = Column(Text, nullable=True)
    trade_id = Column(String(36), nullable=True)
    qdrant_stored = Column(Boolean, nullable=False, default=False)
    mode = Column(String(20), nullable=False, default="paper")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ExchangeCredentialRecord(Base):
    __tablename__ = "exchange_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    exchange = Column(String(50), nullable=False, index=True)
    label = Column(String(100), nullable=True)
    api_key_enc = Column(LargeBinary, nullable=False)
    api_secret_enc = Column(LargeBinary, nullable=False)
    permissions_json = Column(Text, nullable=False, default='["trade","read"]')
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ApprovalRequestRecord(Base):
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    position_usd = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    trade_payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), nullable=True)
