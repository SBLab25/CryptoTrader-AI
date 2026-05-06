"""Phase 4 analytics routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.db.database import get_db_session
from src.db.timescale import SignalLogStore
from src.graph_analysis.correlation import get_graph_info
from src.memory.embeddings import get_model_info
from src.memory.qdrant_client import COLLECTION_SIGNAL_MEMORY, get_collection_info, get_qdrant_client, is_qdrant_available
from src.memory.retriever import get_signal_statistics
from src.memory.signal_store import backfill_unembedded_signals

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


class SignalStats(BaseModel):
    symbol: str
    strategy: Optional[str]
    wins: int
    losses: int
    total_with_outcome: int
    win_rate: Optional[float]
    available: bool


@router.get("/signals/stats", response_model=SignalStats)
async def get_signal_stats(symbol: str = Query(...), strategy: Optional[str] = Query(None)):
    return SignalStats(symbol=symbol, strategy=strategy, **await get_signal_statistics(symbol, strategy))


@router.get("/signals/recent")
async def get_recent_signals(symbol: Optional[str] = Query(None), limit: int = Query(20, ge=1, le=100)):
    async with get_db_session() as session:
        signals = await SignalLogStore.get_recent(session, symbol=symbol, limit=limit)
    for signal in signals:
        if hasattr(signal.get("created_at"), "isoformat"):
            signal["created_at"] = signal["created_at"].isoformat()
    return {"signals": signals, "count": len(signals)}


@router.get("/signals/{signal_id}/similar")
async def get_similar_signals(signal_id: str, limit: int = Query(5, ge=1, le=20), min_similarity: float = Query(0.65, ge=0.0, le=1.0)):
    if not is_qdrant_available():
        raise HTTPException(status_code=503, detail="Qdrant not available")
    client = get_qdrant_client()
    points = client.retrieve(collection_name=COLLECTION_SIGNAL_MEMORY, ids=[signal_id], with_vectors=True)
    if not points:
        raise HTTPException(status_code=404, detail="Signal not found in Qdrant")
    results = client.search(
        collection_name=COLLECTION_SIGNAL_MEMORY,
        query_vector=points[0].vector,
        limit=limit + 1,
        score_threshold=min_similarity,
        with_payload=True,
    )
    return [
        {
            "score": round(hit.score, 4),
            "action": (hit.payload or {}).get("action"),
            "outcome": (hit.payload or {}).get("outcome"),
            "pnl_pct": (hit.payload or {}).get("pnl_pct"),
            "confidence": (hit.payload or {}).get("confidence"),
            "strategy": (hit.payload or {}).get("strategy"),
            "rsi": (hit.payload or {}).get("rsi"),
            "ema_trend": (hit.payload or {}).get("ema_trend"),
            "created_at": (hit.payload or {}).get("created_at"),
        }
        for hit in results
        if str(hit.id) != signal_id
    ][:limit]


@router.get("/correlation/graph")
async def get_correlation_graph():
    return await get_graph_info()


@router.get("/memory/info")
async def get_memory_info():
    return {"qdrant": get_collection_info(), "embeddings": get_model_info()}


@router.post("/memory/backfill")
async def trigger_backfill(batch_size: int = Query(50, ge=1, le=500)):
    return {"embedded": await backfill_unembedded_signals(batch_size=batch_size), "batch_size": batch_size}
