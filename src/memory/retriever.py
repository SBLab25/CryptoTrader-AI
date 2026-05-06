"""Signal-memory retrieval helpers."""

from __future__ import annotations

import asyncio
from typing import Optional

from src.memory.embeddings import embed_indicators
from src.memory.qdrant_client import COLLECTION_SIGNAL_MEMORY, get_qdrant_client, is_qdrant_available

DEFAULT_LIMIT = 5
DEFAULT_MIN_SIMILARITY = 0.70


async def retrieve_similar_signals(
    indicators: dict,
    symbol: str,
    strategy: Optional[str] = None,
    only_wins: bool = False,
    limit: int = DEFAULT_LIMIT,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[dict]:
    if not is_qdrant_available():
        return []
    loop = asyncio.get_event_loop()
    query_vec = await loop.run_in_executor(None, lambda: embed_indicators(indicators, symbol))
    must: list[tuple[str, str]] = [("symbol", symbol)]
    if strategy:
        must.append(("strategy", strategy))
    if only_wins:
        must.append(("outcome", "WIN"))
    results = get_qdrant_client().search(
        collection_name=COLLECTION_SIGNAL_MEMORY,
        query_vector=query_vec,
        query_filter={"must": must},
        limit=limit,
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
            "macd_histogram": (hit.payload or {}).get("macd_histogram"),
            "ema_trend": (hit.payload or {}).get("ema_trend"),
            "created_at": (hit.payload or {}).get("created_at"),
            "signal_log_id": (hit.payload or {}).get("signal_log_id"),
        }
        for hit in results
    ]


def format_rag_context(hits: list[dict]) -> str:
    if not hits:
        return "No similar historical signals found."
    lines = ["Historical analogues for similar market conditions:"]
    for index, hit in enumerate(hits, start=1):
        date = (hit.get("created_at") or "")[:10] or "unknown"
        pnl = hit.get("pnl_pct")
        pnl_str = f"({pnl:+.1f}%)" if pnl is not None else "(pending)"
        rsi = hit.get("rsi")
        rsi_str = f"RSI {rsi:.1f}" if rsi is not None else "RSI ?"
        lines.append(
            f"  {index}. [{date}] {hit.get('action', '?')} -> {hit.get('outcome', 'pending')} {pnl_str}"
            f" | {rsi_str}, trend {hit.get('ema_trend', '?')}"
            f" | confidence {float(hit.get('confidence', 0.0)):.0%}"
            f" | similarity {float(hit.get('score', 0.0)):.0%}"
        )
    return "\n".join(lines)


async def get_signal_statistics(symbol: str, strategy: Optional[str] = None) -> dict:
    if not is_qdrant_available():
        return {"available": False}
    must: list[tuple[str, str]] = [("symbol", symbol)]
    if strategy:
        must.append(("strategy", strategy))
    client = get_qdrant_client()
    wins = client.count(COLLECTION_SIGNAL_MEMORY, count_filter={"must": [*must, ("outcome", "WIN")]}).count
    losses = client.count(COLLECTION_SIGNAL_MEMORY, count_filter={"must": [*must, ("outcome", "LOSS")]}).count
    total_with_outcome = wins + losses
    win_rate = round(wins / total_with_outcome, 4) if total_with_outcome else None
    return {
        "available": True,
        "symbol": symbol,
        "strategy": strategy,
        "wins": wins,
        "losses": losses,
        "total_with_outcome": total_with_outcome,
        "win_rate": win_rate,
    }
