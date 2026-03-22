# File: src/db/database.py
"""
Database Layer — SQLAlchemy async ORM
Persists: trades, signals, portfolio snapshots, backtest results

Fix applied: removed 'from __future__ import annotations' which caused
SQLAlchemy's Mapped[Optional[...]] to break on Windows (and some Linux
setups). Uses classic Column() style instead — works on all platforms
and all Python 3.10+ / SQLAlchemy 2.x versions.
"""
import json
from datetime import datetime
from typing import AsyncGenerator, Optional, List

from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, Text, Integer,
    Index, select, func
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── ORM Models  (classic Column() style — cross-platform safe) ────────────────

class TradeRecord(Base):
    __tablename__ = "trades"

    id               = Column(String(36),  primary_key=True)
    symbol           = Column(String(20),  nullable=False,  index=True)
    side             = Column(String(4),   nullable=False)
    quantity         = Column(Float,       nullable=False)
    entry_price      = Column(Float,       nullable=False)
    stop_loss        = Column(Float,       nullable=False)
    take_profit      = Column(Float,       nullable=False)
    status           = Column(String(12),  default="open",  index=True)
    exchange_order_id= Column(String(64),  nullable=True)

    # Results (nullable — only populated when trade is closed)
    exit_price       = Column(Float,       nullable=True)
    exit_reason      = Column(String(32),  nullable=True)
    pnl              = Column(Float,       nullable=True)
    pnl_pct          = Column(Float,       nullable=True)

    # Metadata
    strategy         = Column(String(32),  default="ai_driven")
    signal_id        = Column(String(36),  nullable=True)
    is_paper         = Column(Boolean,     default=True)
    created_at       = Column(DateTime,    default=datetime.utcnow)
    closed_at        = Column(DateTime,    nullable=True)

    __table_args__ = (
        Index("ix_trades_created_at",    "created_at"),
        Index("ix_trades_symbol_status", "symbol", "status"),
    )


class SignalRecord(Base):
    __tablename__ = "signals"

    id              = Column(String(36),  primary_key=True)
    symbol          = Column(String(20),  nullable=False, index=True)
    signal          = Column(String(16),  nullable=False)
    confidence      = Column(Float,       nullable=False)
    reasoning       = Column(Text,        default="")
    entry_price     = Column(Float,       nullable=False)
    stop_loss       = Column(Float,       nullable=False)
    take_profit     = Column(Float,       nullable=False)
    indicators_json = Column(Text,        nullable=True)
    ai_analysis     = Column(Text,        nullable=True)
    timestamp       = Column(DateTime,    default=datetime.utcnow, index=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id                  = Column(Integer,  primary_key=True, autoincrement=True)
    total_value         = Column(Float,    nullable=False)
    available_balance   = Column(Float,    nullable=False)
    invested_value      = Column(Float,    nullable=False)
    total_pnl           = Column(Float,    nullable=False)
    total_pnl_pct       = Column(Float,    nullable=False)
    daily_pnl           = Column(Float,    nullable=False)
    open_positions_count= Column(Integer,  default=0)
    is_paper            = Column(Boolean,  default=True)
    recorded_at         = Column(DateTime, default=datetime.utcnow, index=True)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    strategy         = Column(String(32), nullable=False, index=True)
    symbol           = Column(String(20), nullable=False)
    timeframe        = Column(String(8),  default="1h")
    start_date       = Column(String(20), nullable=False)
    end_date         = Column(String(20), nullable=False)
    initial_capital  = Column(Float,      nullable=False)
    final_capital    = Column(Float,      nullable=False)
    total_return_pct = Column(Float,      nullable=False)
    total_trades     = Column(Integer,    nullable=False)
    winning_trades   = Column(Integer,    nullable=False)
    win_rate         = Column(Float,      nullable=False)
    max_drawdown_pct = Column(Float,      nullable=False)
    sharpe_ratio     = Column(Float,      nullable=True)
    profit_factor    = Column(Float,      nullable=True)
    metrics_json     = Column(Text,       nullable=True)
    created_at       = Column(DateTime,   default=datetime.utcnow)


# ── Engine & Session Factory ──────────────────────────────────────────────────

_engine: Optional[AsyncEngine] = None
_session_factory = None


def _make_db_url(url: str) -> str:
    """Convert sync SQLAlchemy URL to the correct async driver URL."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


async def init_db() -> None:
    """Initialize the database — creates all tables if they don't exist."""
    global _engine, _session_factory

    db_url = _make_db_url(settings.database_url)
    logger.info(f"[DB] Initializing: {db_url[:50]}...")

    _engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
    )
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("[DB] Database initialized ✓")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    if _session_factory is None:
        await init_db()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("[DB] Connection closed")


# ── Repository Functions ──────────────────────────────────────────────────────

async def save_trade(session: AsyncSession, trade_data: dict) -> TradeRecord:
    record = TradeRecord(**trade_data)
    session.add(record)
    await session.flush()
    return record


async def update_trade(session: AsyncSession, trade_id: str, updates: dict) -> None:
    record = await session.get(TradeRecord, trade_id)
    if record:
        for k, v in updates.items():
            setattr(record, k, v)
        await session.flush()


async def get_trade_history(
    session: AsyncSession,
    limit: int = 100,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
) -> List[TradeRecord]:
    stmt = select(TradeRecord).order_by(TradeRecord.created_at.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(TradeRecord.symbol == symbol)
    if status:
        stmt = stmt.where(TradeRecord.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


async def save_signal(session: AsyncSession, signal_data: dict) -> SignalRecord:
    indicators = signal_data.pop("indicators", {})
    record = SignalRecord(
        **signal_data,
        indicators_json=json.dumps(indicators) if indicators else None,
    )
    session.add(record)
    await session.flush()
    return record


async def save_portfolio_snapshot(
    session: AsyncSession, snapshot_data: dict
) -> PortfolioSnapshot:
    record = PortfolioSnapshot(**snapshot_data)
    session.add(record)
    await session.flush()
    return record


async def get_portfolio_history(
    session: AsyncSession,
    limit: int = 288,
) -> List[PortfolioSnapshot]:
    stmt = (
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(reversed(result.scalars().all()))


async def get_trade_stats(session: AsyncSession) -> dict:
    total     = await session.scalar(select(func.count(TradeRecord.id)))
    wins      = await session.scalar(
        select(func.count(TradeRecord.id)).where(TradeRecord.pnl > 0)
    )
    total_pnl = await session.scalar(select(func.sum(TradeRecord.pnl))) or 0
    avg_win   = await session.scalar(
        select(func.avg(TradeRecord.pnl)).where(TradeRecord.pnl > 0)
    ) or 0
    avg_loss  = await session.scalar(
        select(func.avg(TradeRecord.pnl)).where(TradeRecord.pnl < 0)
    ) or 0

    return {
        "total_trades":   total or 0,
        "winning_trades": wins or 0,
        "win_rate_pct":   round((wins / total * 100) if total else 0, 2),
        "total_pnl":      round(total_pnl, 4),
        "avg_win":        round(avg_win, 4),
        "avg_loss":       round(avg_loss, 4),
    }
