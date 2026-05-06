"""Phase 3 risk node."""

from __future__ import annotations

import time

from src.agents.graph.runtime import portfolio_agent
from src.core.models import Portfolio, SignalStrength, TradeSignal
from src.db.database import get_db_session
from src.db.timescale import SignalLogStore
from src.risk.engine import risk_engine

_ACTION_MAP = {
    "BUY": SignalStrength.BUY,
    "SELL": SignalStrength.SELL,
    "STRONG_BUY": SignalStrength.STRONG_BUY,
    "STRONG_SELL": SignalStrength.STRONG_SELL,
    "NEUTRAL": SignalStrength.NEUTRAL,
    "HOLD": SignalStrength.NEUTRAL,
}


def _portfolio_from_state(state: dict) -> Portfolio:
    snapshot = state.get("portfolio")
    if isinstance(snapshot, Portfolio):
        return snapshot
    if isinstance(snapshot, dict) and "available_balance" in snapshot:
        data = dict(snapshot)
        data.setdefault("open_positions", [])
        data.setdefault("is_paper", True)
        return Portfolio(**data)
    prices = {state["symbol"]: float(state["tick"]["close"])}
    return portfolio_agent.get_portfolio_snapshot(prices)


def _trade_signal_from_state(state: dict) -> TradeSignal | None:
    signal = state.get("signal") or {}
    action = (signal.get("action") or "HOLD").upper()
    if action == "HOLD":
        return None
    return TradeSignal(
        id=signal.get("id") or state.get("cycle_id"),
        symbol=state["symbol"],
        signal=_ACTION_MAP[action],
        confidence=float(signal.get("confidence", 0.0)),
        reasoning=signal.get("reasoning", ""),
        entry_price=float(signal.get("entry_price") or state["tick"]["close"]),
        stop_loss=float(signal.get("stop_loss") or state["tick"]["close"]),
        take_profit=float(signal.get("take_profit") or state["tick"]["close"]),
        indicators=signal.get("indicators") or ((state.get("indicators") or {}).get("raw") or {}),
        ai_analysis=signal.get("ai_analysis"),
    )


async def _update_signal_log(signal_id: str | None, passed: bool, reason: str | None = None, trade_id: str | None = None) -> None:
    if not signal_id:
        return
    async with get_db_session() as session:
        await SignalLogStore.update_risk_result(
            session,
            signal_id=signal_id,
            passed=passed,
            rejection_reason=reason,
            trade_id=trade_id,
        )


async def risk_engine_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        signal = _trade_signal_from_state(state)
        if signal is None:
            result = {
                "passed": False,
                "rejected_by_layer": 0,
                "rejection_reason": "HOLD signal is not tradable",
                "approved_position_usd": 0.0,
            }
            return {
                "risk_result": result,
                "errors": [],
                "node_timings": {"risk_engine": round((time.monotonic() - started) * 1000, 2)},
            }

        portfolio = _portfolio_from_state(state)
        assessment = risk_engine.assess_trade(signal, portfolio, len(portfolio.open_positions))
        if assessment.approved:
            correlated_ok, correlated_reason = await _check_correlation_exposure(
                state["symbol"], [position.symbol for position in portfolio.open_positions]
            )
            if not correlated_ok:
                assessment.approved = False
                assessment.reason = correlated_reason
            result = {
                "passed": assessment.approved,
                "rejected_by_layer": None if assessment.approved else 9,
                "rejection_reason": None if assessment.approved else assessment.reason,
                "approved_position_usd": round(assessment.trade_size * signal.entry_price, 4),
                "trade_size": assessment.trade_size,
                "risk_amount": assessment.risk_amount,
                "risk_pct": assessment.risk_pct,
                "warnings": assessment.warnings,
            }
            await _update_signal_log(signal.id, assessment.approved, reason=None if assessment.approved else assessment.reason)
        else:
            reason = assessment.reason or "Risk validation failed"
            rejected_by_layer = 1
            if "Max open positions" in reason:
                rejected_by_layer = 2
            elif "confidence too low" in reason:
                rejected_by_layer = 3
            elif "Risk/Reward ratio" in reason:
                rejected_by_layer = 5
            result = {
                "passed": False,
                "rejected_by_layer": rejected_by_layer,
                "rejection_reason": reason,
                "approved_position_usd": round(assessment.trade_size * signal.entry_price, 4),
                "trade_size": assessment.trade_size,
                "risk_amount": assessment.risk_amount,
                "risk_pct": assessment.risk_pct,
                "warnings": assessment.warnings,
            }
            await _update_signal_log(signal.id, False, reason=reason)
        return {
            "risk_result": result,
            "portfolio": portfolio.model_dump(mode="json"),
            "errors": [],
            "node_timings": {"risk_engine": round((time.monotonic() - started) * 1000, 2)},
        }
    except Exception as exc:
        return {
            "risk_result": {
                "passed": False,
                "rejected_by_layer": 9,
                "rejection_reason": str(exc),
                "approved_position_usd": 0.0,
            },
            "errors": [f"risk_engine_node failed: {exc}"],
            "node_timings": {"risk_engine": round((time.monotonic() - started) * 1000, 2)},
        }


async def _check_correlation_exposure(symbol: str, open_positions: list[str]) -> tuple[bool, str]:
    try:
        from src.graph_analysis.correlation import check_correlated_exposure

        return await check_correlated_exposure(symbol, open_positions)
    except Exception:
        return True, ""
