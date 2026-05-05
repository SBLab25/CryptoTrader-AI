"""Additional ORM models introduced by Phase 1."""

from datetime import datetime
from uuid import uuid4

from passlib.context import CryptContext
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

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
