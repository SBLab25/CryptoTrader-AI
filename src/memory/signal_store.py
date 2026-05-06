"""Signal-memory persistence helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.db.database import get_db_session
from src.memory.embeddings import _build_signal_text, embed_batch, embed_signal
from src.memory.qdrant_client import COLLECTION_SIGNAL_MEMORY, PointStruct, get_qdrant_client


async def store_signal(
    signal_id: str,
    symbol: str,
    action: str,
    confidence: float,
    strategy: str,
    reasoning: str,
    indicators: dict,
    llm_provider: str = "",
    mode: str = "paper",
    trade_id: str | None = None,
) -> bool:
    try:
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None,
            lambda: embed_signal(reasoning=reasoning, indicators=indicators, symbol=symbol, action=action, strategy=strategy),
        )
        payload = {
            "symbol": symbol,
            "strategy": strategy,
            "action": action,
            "confidence": float(confidence),
            "outcome": None,
            "pnl_pct": None,
            "rsi": indicators.get("rsi"),
            "macd_histogram": indicators.get("macd_histogram"),
            "bb_percent_b": indicators.get("bb_percent_b"),
            "ema_trend": indicators.get("ema_trend"),
            "atr": indicators.get("atr"),
            "llm_provider": llm_provider,
            "mode": mode,
            "signal_log_id": signal_id,
            "trade_id": trade_id,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        get_qdrant_client().upsert(
            collection_name=COLLECTION_SIGNAL_MEMORY,
            points=[PointStruct(id=signal_id, vector=vector, payload=payload)],
        )
        asyncio.create_task(_mark_stored_in_db(signal_id))
        return True
    except Exception:
        return False


async def update_outcome(signal_id: str, outcome: str, pnl_pct: float, trade_id: str | None = None) -> bool:
    try:
        get_qdrant_client().set_payload(
            collection_name=COLLECTION_SIGNAL_MEMORY,
            payload={"outcome": outcome, "pnl_pct": round(float(pnl_pct), 4), "trade_id": trade_id},
            points=[signal_id],
        )
        return True
    except Exception:
        return False


async def backfill_unembedded_signals(batch_size: int = 50) -> int:
    from sqlalchemy import select

    from src.db.models import SignalLogRecord

    async with get_db_session() as session:
        result = await session.execute(
            select(SignalLogRecord)
            .where(SignalLogRecord.qdrant_stored.is_(False))
            .where(SignalLogRecord.action != "HOLD")
            .order_by(SignalLogRecord.created_at.asc())
            .limit(batch_size)
        )
        rows = result.scalars().all()
    if not rows:
        return 0

    texts = []
    for row in rows:
        texts.append(
            _build_signal_text(
                reasoning=row.reasoning or "",
                indicators={
                    "rsi": row.rsi,
                    "macd_histogram": row.macd_histogram,
                    "bb_percent_b": row.bb_percent_b,
                    "ema_trend": row.ema_trend,
                    "atr": row.atr,
                },
                symbol=row.symbol,
                action=row.action,
                strategy=row.strategy or "",
            )
        )
    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(None, lambda: embed_batch(texts))
    points = []
    for row, vector in zip(rows, vectors):
        points.append(
            PointStruct(
                id=str(row.id),
                vector=vector,
                payload={
                    "symbol": row.symbol,
                    "strategy": row.strategy,
                    "action": row.action,
                    "confidence": float(row.confidence or 0.0),
                    "outcome": None,
                    "pnl_pct": None,
                    "rsi": row.rsi,
                    "macd_histogram": row.macd_histogram,
                    "bb_percent_b": row.bb_percent_b,
                    "ema_trend": row.ema_trend,
                    "atr": row.atr,
                    "llm_provider": row.llm_provider,
                    "mode": row.mode or "paper",
                    "signal_log_id": str(row.id),
                    "trade_id": row.trade_id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                },
            )
        )
    get_qdrant_client().upsert(collection_name=COLLECTION_SIGNAL_MEMORY, points=points)
    async with get_db_session() as session:
        for row in rows:
            record = await session.get(type(row), row.id)
            if record is not None:
                record.qdrant_stored = True
        await session.commit()
    return len(rows)


async def _mark_stored_in_db(signal_id: str) -> None:
    from src.db.models import SignalLogRecord

    async with get_db_session() as session:
        record = await session.get(SignalLogRecord, signal_id)
        if record is not None:
            record.qdrant_stored = True
            await session.commit()
