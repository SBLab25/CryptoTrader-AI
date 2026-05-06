"""Phase 3 execution node."""

from __future__ import annotations

import time

from src.agents.graph.nodes.risk_engine import _trade_signal_from_state
from src.agents.graph.runtime import execution_agent, portfolio_agent
from src.core.models import RiskAssessment
from src.db.database import get_db_session
from src.db.timescale import SignalLogStore


async def _update_signal_trade(signal_id: str | None, trade_id: str | None) -> None:
    if not signal_id or not trade_id:
        return
    async with get_db_session() as session:
        await SignalLogStore.update_risk_result(session, signal_id=signal_id, passed=True, trade_id=trade_id)


async def execution_agent_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        if not state.get("approval_granted"):
            return {
                "execution_result": {"status": "skipped", "reason": "approval_denied"},
                "errors": [],
                "node_timings": {"execution_agent": round((time.monotonic() - started) * 1000, 2)},
            }

        signal = _trade_signal_from_state(state)
        if signal is None:
            return {
                "execution_result": {"status": "skipped", "reason": "no_signal"},
                "errors": [],
                "node_timings": {"execution_agent": round((time.monotonic() - started) * 1000, 2)},
            }

        risk_data = state.get("risk_result") or {}
        risk = RiskAssessment(
            approved=True,
            symbol=signal.symbol,
            trade_size=float(risk_data.get("trade_size", 0.0)),
            risk_amount=float(risk_data.get("risk_amount", 0.0)),
            risk_pct=float(risk_data.get("risk_pct", 0.0)),
            warnings=list(risk_data.get("warnings") or []),
        )
        trade = await execution_agent.execute_trade(signal, risk, is_paper=str(state.get("mode", "paper")).lower() != "live")
        if trade is None:
            return {
                "execution_result": {"status": "failed"},
                "errors": [],
                "node_timings": {"execution_agent": round((time.monotonic() - started) * 1000, 2)},
            }

        cost = trade.quantity * trade.entry_price
        portfolio_agent.record_trade_opened(trade, cost)
        await _update_signal_trade(signal.id, trade.id)
        return {
            "trade": trade.model_dump(mode="json"),
            "execution_result": {"status": "filled", "trade_id": trade.id, "order_id": trade.exchange_order_id},
            "errors": [],
            "node_timings": {"execution_agent": round((time.monotonic() - started) * 1000, 2)},
        }
    except Exception as exc:
        return {
            "execution_result": {"status": "error", "reason": str(exc)},
            "errors": [f"execution_agent_node failed: {exc}"],
            "node_timings": {"execution_agent": round((time.monotonic() - started) * 1000, 2)},
        }
