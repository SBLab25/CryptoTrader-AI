"""Trade outcome feedback loop into signal memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class TradeOutcome:
    signal_id: str
    symbol: str
    pnl: float
    pnl_pct: float
    hold_hours: float
    close_reason: str
    win: bool


class OutcomeFeedback:
    def __init__(self, signal_memory=None, audit=None, metrics=None) -> None:
        self._memory = signal_memory
        self._audit = audit
        self._metrics = metrics

    async def record_trade_outcome(
        self,
        signal_id: str,
        symbol: str,
        pnl: float,
        pnl_pct: float,
        hold_hours: float,
        close_reason: str,
    ) -> None:
        outcome = TradeOutcome(
            signal_id=signal_id,
            symbol=symbol,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_hours=hold_hours,
            close_reason=close_reason,
            win=pnl > 0,
        )

        if self._memory and signal_id:
            try:
                updater = getattr(self._memory, "update_outcome", None)
                if updater is not None:
                    result = updater(signal_id=signal_id, pnl=pnl, pnl_pct=pnl_pct)
                    if hasattr(result, "__await__"):
                        await result
                log.info(
                    "outcome_feedback_stored",
                    signal_id=signal_id,
                    symbol=symbol,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 4),
                    close_reason=close_reason,
                )
            except Exception as exc:
                log.warning("outcome_feedback_store_failed", signal_id=signal_id, error=str(exc))

        if self._audit:
            try:
                audit_result = self._audit(
                    event_type="TRADE_CLOSED",
                    entity_id=signal_id or symbol,
                    entity_type="TradeOutcome",
                    actor="system",
                    details={
                        "symbol": symbol,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 4),
                        "hold_hours": round(hold_hours, 2),
                        "close_reason": close_reason,
                        "win": outcome.win,
                    },
                )
                if hasattr(audit_result, "__await__"):
                    await audit_result
            except Exception:
                pass

    async def get_feedback_stats(self) -> dict[str, Any]:
        if not self._memory:
            return {"available": False, "reason": "no signal_memory configured"}

        stats_fn = getattr(self._memory, "collection_stats", None)
        if stats_fn is None:
            return {"available": False, "reason": "collection_stats unavailable"}

        try:
            stats = stats_fn()
            if hasattr(stats, "__await__"):
                stats = await stats
            return {
                "available": True,
                "vectors_total": int(stats.get("vectors_count", 0)),
                "indexed": int(stats.get("indexed_vectors_count", 0)),
                "status": stats.get("status", "unknown"),
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}
