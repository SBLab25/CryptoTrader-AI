# File: src/api/routes/history.py
"""
Trade History & Analytics API Routes
Full CRUD + analytics for trades, signals, portfolio history.
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import (
    get_session,
    get_trade_history,
    get_portfolio_history,
    get_trade_stats,
    TradeRecord,
    PortfolioSnapshot,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["History & Analytics"])


# ── Trade History ─────────────────────────────────────────────────────────────

@router.get("/trades")
async def list_trades(
    limit: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|filled|cancelled|failed)$"),
    session: AsyncSession = Depends(get_session),
):
    """
    Get trade history with optional filters.
    Returns most recent trades first.
    """
    trades = await get_trade_history(session, limit=limit, symbol=symbol, status=status)
    return [_trade_to_dict(t) for t in trades]


@router.get("/trades/{trade_id}")
async def get_trade(
    trade_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single trade by ID"""
    record = await session.get(TradeRecord, trade_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return _trade_to_dict(record)


@router.get("/trades/stats/summary")
async def trade_stats(session: AsyncSession = Depends(get_session)):
    """Aggregate statistics from all closed trades in the database"""
    return await get_trade_stats(session)


# ── Portfolio History ─────────────────────────────────────────────────────────

@router.get("/portfolio/history")
async def portfolio_history(
    limit: int = Query(288, ge=1, le=2000),  # 288 = 24h at 5-min intervals
    session: AsyncSession = Depends(get_session),
):
    """
    Get historical portfolio snapshots for charting.
    Returns chronologically ordered list.
    """
    snapshots = await get_portfolio_history(session, limit=limit)
    return [
        {
            "total_value": s.total_value,
            "available_balance": s.available_balance,
            "invested_value": s.invested_value,
            "total_pnl": s.total_pnl,
            "total_pnl_pct": s.total_pnl_pct,
            "daily_pnl": s.daily_pnl,
            "open_positions": s.open_positions_count,
            "recorded_at": s.recorded_at.isoformat(),
        }
        for s in snapshots
    ]


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics/pnl-by-symbol")
async def pnl_by_symbol(session: AsyncSession = Depends(get_session)):
    """PnL breakdown by symbol"""
    from sqlalchemy import select, func
    stmt = (
        select(
            TradeRecord.symbol,
            func.count(TradeRecord.id).label("trades"),
            func.sum(TradeRecord.pnl).label("total_pnl"),
            func.avg(TradeRecord.pnl).label("avg_pnl"),
        )
        .where(TradeRecord.pnl.isnot(None))
        .group_by(TradeRecord.symbol)
        .order_by(func.sum(TradeRecord.pnl).desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "symbol": row.symbol,
            "trades": row.trades,
            "total_pnl": round(row.total_pnl or 0, 4),
            "avg_pnl": round(row.avg_pnl or 0, 4),
        }
        for row in result
    ]


@router.get("/analytics/win-loss-by-hour")
async def win_loss_by_hour(session: AsyncSession = Depends(get_session)):
    """Trading performance breakdown by hour of day (UTC)"""
    from sqlalchemy import select, func, extract, case
    stmt = (
        select(
            extract("hour", TradeRecord.created_at).label("hour"),
            func.count(TradeRecord.id).label("total"),
            func.sum(case((TradeRecord.pnl > 0, 1), else_=0)).label("wins"),
            func.sum(TradeRecord.pnl).label("total_pnl"),
        )
        .where(TradeRecord.pnl.isnot(None))
        .group_by(extract("hour", TradeRecord.created_at))
        .order_by(extract("hour", TradeRecord.created_at))
    )
    result = await session.execute(stmt)
    rows = []
    for row in result:
        total = row.total or 0
        wins = row.wins or 0
        rows.append({
            "hour_utc": int(row.hour),
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate_pct": round(wins / total * 100, 1) if total else 0,
            "total_pnl": round(row.total_pnl or 0, 4),
        })
    return rows


@router.get("/analytics/strategy-performance")
async def strategy_performance(session: AsyncSession = Depends(get_session)):
    """Performance breakdown by strategy"""
    from sqlalchemy import select, func, case
    stmt = (
        select(
            TradeRecord.strategy,
            func.count(TradeRecord.id).label("trades"),
            func.sum(case((TradeRecord.pnl > 0, 1), else_=0)).label("wins"),
            func.sum(TradeRecord.pnl).label("total_pnl"),
            func.avg(TradeRecord.pnl).label("avg_pnl"),
        )
        .where(TradeRecord.pnl.isnot(None))
        .group_by(TradeRecord.strategy)
        .order_by(func.sum(TradeRecord.pnl).desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "strategy": row.strategy,
            "trades": row.trades,
            "wins": row.wins or 0,
            "win_rate_pct": round((row.wins or 0) / row.trades * 100, 1) if row.trades else 0,
            "total_pnl": round(row.total_pnl or 0, 4),
            "avg_pnl": round(row.avg_pnl or 0, 4),
        }
        for row in result
    ]


@router.get("/analytics/equity-drawdown")
async def equity_drawdown(
    limit: int = Query(500),
    session: AsyncSession = Depends(get_session),
):
    """Compute drawdown series from portfolio history"""
    snapshots = await get_portfolio_history(session, limit=limit)
    if not snapshots:
        return {"equity": [], "drawdown": [], "timestamps": []}

    values = [s.total_value for s in snapshots]
    timestamps = [s.recorded_at.isoformat() for s in snapshots]

    peak = values[0]
    drawdowns = []
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        drawdowns.append(round(dd, 3))

    return {
        "equity": [round(v, 2) for v in values],
        "drawdown": drawdowns,
        "timestamps": timestamps,
        "max_drawdown_pct": round(max(drawdowns), 3) if drawdowns else 0,
        "current_drawdown_pct": round(drawdowns[-1], 3) if drawdowns else 0,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trade_to_dict(t: TradeRecord) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "side": t.side,
        "quantity": t.quantity,
        "entry_price": t.entry_price,
        "stop_loss": t.stop_loss,
        "take_profit": t.take_profit,
        "status": t.status,
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "pnl": t.pnl,
        "pnl_pct": t.pnl_pct,
        "strategy": t.strategy,
        "is_paper": t.is_paper,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }
