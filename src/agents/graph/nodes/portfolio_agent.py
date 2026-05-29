"""Phase 3 portfolio node."""

from __future__ import annotations

import time

from src.agents.graph.runtime import portfolio_agent
from src.db.redis_client import broadcast
from src.notifications.ntfy import NtfyClient
from src.stability.outcome_feedback import OutcomeFeedback


async def portfolio_agent_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        price = float(state["tick"]["close"])
        portfolio = portfolio_agent.get_portfolio_snapshot({state["symbol"]: price})
        payload = portfolio.model_dump(mode="json")
        closed_trade = state.get("closed_trade")
        if closed_trade:
            ntfy = NtfyClient()
            try:
                await ntfy.trade_closed(
                    symbol=closed_trade["symbol"],
                    pnl=float(closed_trade.get("pnl", 0.0)),
                    pnl_pct=float(closed_trade.get("pnl_pct", 0.0)) / 100.0,
                    reason=str(closed_trade.get("exit_reason", "")),
                    mode=str(state.get("mode", "paper")).lower(),
                )
            except Exception:
                pass
            feedback = OutcomeFeedback(signal_memory=state.get("signal_memory"))
            try:
                await feedback.record_trade_outcome(
                    signal_id=str(closed_trade.get("signal_id") or ""),
                    symbol=str(closed_trade.get("symbol")),
                    pnl=float(closed_trade.get("pnl", 0.0)),
                    pnl_pct=float(closed_trade.get("pnl_pct", 0.0)) / 100.0,
                    hold_hours=float(closed_trade.get("hold_hours", 0.0)),
                    close_reason=str(closed_trade.get("exit_reason", "manual")),
                )
            except Exception:
                pass
        try:
            await broadcast({"type": "portfolio", "data": payload})
        except Exception:
            pass
        return {
            "portfolio": payload,
            "errors": [],
            "node_timings": {"portfolio_agent": round((time.monotonic() - started) * 1000, 2)},
        }
    except Exception as exc:
        return {
            "errors": [f"portfolio_agent_node failed: {exc}"],
            "node_timings": {"portfolio_agent": round((time.monotonic() - started) * 1000, 2)},
        }
