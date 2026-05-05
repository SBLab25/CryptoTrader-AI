"""Phase 2 storage helpers kept backend-agnostic for SQLite and Postgres."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Optional
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.models import OHLCV
from src.db.models import ExchangeCredentialRecord, OHLCVRecord, SignalLogRecord


def _fernet_for(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


class OHLCVStore:
    @staticmethod
    async def insert_tick(session: AsyncSession, tick: OHLCV) -> None:
        existing = await session.get(OHLCVRecord, {"timestamp": tick.timestamp, "symbol": tick.symbol})
        if existing is None:
            session.add(
                OHLCVRecord(
                    timestamp=tick.timestamp,
                    symbol=tick.symbol,
                    open=tick.open,
                    high=tick.high,
                    low=tick.low,
                    close=tick.close,
                    volume=tick.volume,
                    source=tick.source,
                )
            )
            await session.commit()

    @staticmethod
    async def insert_ticks_batch(session: AsyncSession, ticks: list[OHLCV]) -> int:
        inserted = 0
        for tick in ticks:
            existing = await session.get(OHLCVRecord, {"timestamp": tick.timestamp, "symbol": tick.symbol})
            if existing is None:
                session.add(
                    OHLCVRecord(
                        timestamp=tick.timestamp,
                        symbol=tick.symbol,
                        open=tick.open,
                        high=tick.high,
                        low=tick.low,
                        close=tick.close,
                        volume=tick.volume,
                        source=tick.source,
                    )
                )
                inserted += 1
        await session.commit()
        return inserted

    @staticmethod
    async def get_latest(session: AsyncSession, symbol: str, limit: int = 200) -> list[dict]:
        result = await session.execute(
            select(OHLCVRecord)
            .where(OHLCVRecord.symbol == symbol)
            .order_by(OHLCVRecord.timestamp.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        return [
            {
                "timestamp": row.timestamp,
                "symbol": row.symbol,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "source": row.source,
            }
            for row in rows
        ]


class SignalLogStore:
    @staticmethod
    async def insert(session: AsyncSession, record: dict) -> str:
        signal_id = record.get("id") or str(uuid4())
        session.add(
            SignalLogRecord(
                id=signal_id,
                symbol=record["symbol"],
                strategy=record.get("strategy", "ai_llm_ta"),
                action=record["action"],
                confidence=float(record.get("confidence", 0.0)),
                stop_loss=record.get("stop_loss"),
                take_profit=record.get("take_profit"),
                entry_price=record.get("entry_price"),
                rsi=record.get("rsi"),
                macd_histogram=record.get("macd_histogram"),
                bb_percent_b=record.get("bb_percent_b"),
                ema_trend=record.get("ema_trend"),
                atr=record.get("atr"),
                reasoning=record.get("reasoning"),
                llm_provider=record.get("llm_provider"),
                llm_model=record.get("llm_model"),
                llm_latency_ms=record.get("llm_latency_ms"),
                risk_passed=record.get("risk_passed"),
                rejection_reason=record.get("rejection_reason"),
                trade_id=record.get("trade_id"),
                qdrant_stored=bool(record.get("qdrant_stored", False)),
                mode=record.get("mode", settings.trading_mode),
            )
        )
        await session.commit()
        return signal_id

    @staticmethod
    async def update_risk_result(
        session: AsyncSession,
        signal_id: str,
        passed: bool,
        rejection_reason: Optional[str] = None,
        trade_id: Optional[str] = None,
    ) -> None:
        record = await session.get(SignalLogRecord, signal_id)
        if record is None:
            return
        record.risk_passed = passed
        record.rejection_reason = rejection_reason
        if trade_id is not None:
            record.trade_id = trade_id
        await session.commit()

    @staticmethod
    async def get_recent(session: AsyncSession, symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
        stmt = select(SignalLogRecord).order_by(SignalLogRecord.created_at.desc()).limit(limit)
        if symbol:
            stmt = stmt.where(SignalLogRecord.symbol == symbol)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": row.id,
                "symbol": row.symbol,
                "strategy": row.strategy,
                "action": row.action,
                "confidence": row.confidence,
                "risk_passed": row.risk_passed,
                "rejection_reason": row.rejection_reason,
                "llm_provider": row.llm_provider,
                "reasoning": row.reasoning,
                "created_at": row.created_at,
            }
            for row in rows
        ]


class CredentialStore:
    @staticmethod
    async def save(
        session: AsyncSession,
        exchange: str,
        api_key: str,
        api_secret: str,
        vault_key: str,
        label: Optional[str] = None,
        permissions: Optional[list[str]] = None,
    ) -> str:
        perms = permissions or ["trade", "read"]
        if "withdraw" in perms:
            raise ValueError("Withdraw permission is explicitly prohibited")
        cred_id = str(uuid4())
        fernet = _fernet_for(vault_key)
        session.add(
            ExchangeCredentialRecord(
                id=cred_id,
                exchange=exchange,
                label=label,
                api_key_enc=fernet.encrypt(api_key.encode("utf-8")),
                api_secret_enc=fernet.encrypt(api_secret.encode("utf-8")),
                permissions_json=json.dumps(perms),
                is_active=True,
            )
        )
        await session.commit()
        return cred_id

    @staticmethod
    async def load(session: AsyncSession, exchange: str, vault_key: str) -> Optional[dict]:
        result = await session.execute(
            select(ExchangeCredentialRecord)
            .where(ExchangeCredentialRecord.exchange == exchange)
            .where(ExchangeCredentialRecord.is_active.is_(True))
            .order_by(ExchangeCredentialRecord.created_at.desc())
            .limit(1)
        )
        record = result.scalars().first()
        if record is None:
            return None
        fernet = _fernet_for(vault_key)
        return {
            "id": record.id,
            "api_key": fernet.decrypt(record.api_key_enc).decode("utf-8"),
            "api_secret": fernet.decrypt(record.api_secret_enc).decode("utf-8"),
            "permissions": json.loads(record.permissions_json),
        }

    @staticmethod
    async def deactivate(session: AsyncSession, exchange: str) -> None:
        result = await session.execute(
            select(ExchangeCredentialRecord).where(ExchangeCredentialRecord.exchange == exchange)
        )
        for record in result.scalars().all():
            record.is_active = False
        await session.commit()
