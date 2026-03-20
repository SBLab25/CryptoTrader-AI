# File: src/db/database.py
"""
Database Layer — SQLAlchemy async models
Persists: trades, signals, portfolio snapshots, performance metrics
"""
from __future__ import annotations

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
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── ORM Models ────────────────────────────────────────────────────────────────

class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Results
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    strategy: Mapped[str] = mapped_column(String(32), default="ai_driven")
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_trades_created_at", "created_at"),
        Index("ix_trades_symbol_status", "symbol", "status"),
    )


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    indicators_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    available_balance: Mapped[float] = mapped_column(Float, nullable=False)
    invested_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    total_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    daily_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    start_date: Mapped[str] = mapped_column(String(20), nullable=False)
    end_date: Mapped[str] = mapped_column(String(20), nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    final_capital: Mapped[float] = mapped_column(Float, nullable=False)
    total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Engine & Session Factory ──────────────────────────────────────────────────

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def _make_db_url(url: str) -> str:
    """Convert sync SQLAlchemy URL to async driver"""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


async def init_db() -> None:
    """Initialize the database — create tables if they don't exist"""
    global _engine, _session_factory

    db_url = _make_db_url(settings.database_url)
    logger.info(f"[DB] Initializing database: {db_url[:40]}...")

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
    """FastAPI dependency — yields a database session"""
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
        logger.info("[DB] Database connection closed")


# ── Repository Functions ──────────────────────────────────────────────────────

async def save_trade(session: AsyncSession, trade_data: dict) -> TradeRecord:
    record = TradeRecord(**trade_data)
    session.add(record)
    await session.flush()
    return record


async def update_trade(session: AsyncSession, trade_id: str, updates: dict) -> None:
    result = await session.get(TradeRecord, trade_id)
    if result:
        for k, v in updates.items():
            setattr(result, k, v)
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


async def save_portfolio_snapshot(session: AsyncSession, snapshot_data: dict) -> PortfolioSnapshot:
    record = PortfolioSnapshot(**snapshot_data)
    session.add(record)
    await session.flush()
    return record


async def get_portfolio_history(
    session: AsyncSession,
    limit: int = 288,  # 24h at 5-min intervals
) -> List[PortfolioSnapshot]:
    stmt = (
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(reversed(result.scalars().all()))


async def get_trade_stats(session: AsyncSession) -> dict:
    """Aggregate trade statistics from DB"""
    total = await session.scalar(select(func.count(TradeRecord.id)))
    wins = await session.scalar(
        select(func.count(TradeRecord.id)).where(TradeRecord.pnl > 0)
    )
    total_pnl = await session.scalar(select(func.sum(TradeRecord.pnl))) or 0
    avg_win = await session.scalar(
        select(func.avg(TradeRecord.pnl)).where(TradeRecord.pnl > 0)
    ) or 0
    avg_loss = await session.scalar(
        select(func.avg(TradeRecord.pnl)).where(TradeRecord.pnl < 0)
    ) or 0

    return {
        "total_trades": total or 0,
        "winning_trades": wins or 0,
        "win_rate_pct": round((wins / total * 100) if total else 0, 2),
        "total_pnl": round(total_pnl, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
    }
