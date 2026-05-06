"""Phase 3 lightweight trading graph."""

from __future__ import annotations

import uuid
from typing import Optional

from langgraph.graph import END, StateGraph

from src.agents.graph.checkpointing.redis_checkpointer import RedisCheckpointer
from src.agents.graph.nodes import (
    approval_gate_node,
    execution_agent_node,
    market_analyst_node,
    portfolio_agent_node,
    risk_engine_node,
    signal_agent_node,
)
from src.core.config import settings

_graph_instance = None


def _route_after_market_analyst(state: dict) -> str:
    if not state.get("indicators") or not state.get("ohlcv"):
        return END
    return "signal_agent"


def _route_after_signal_agent(state: dict) -> str:
    signal = state.get("signal")
    if not signal or signal.get("action") == "HOLD":
        return END
    return "risk_engine"


def _route_after_risk_engine(state: dict) -> str:
    if not (state.get("risk_result") or {}).get("passed"):
        return END
    return "approval_gate"


def _route_after_approval_gate(state: dict) -> str:
    if state.get("approval_granted"):
        return "execution_agent"
    return END


def build_trading_graph(checkpointer: Optional[RedisCheckpointer] = None):
    workflow = StateGraph(dict)
    workflow.add_node("market_analyst", market_analyst_node)
    workflow.add_node("signal_agent", signal_agent_node)
    workflow.add_node("risk_engine", risk_engine_node)
    workflow.add_node("approval_gate", approval_gate_node)
    workflow.add_node("execution_agent", execution_agent_node)
    workflow.add_node("portfolio_agent", portfolio_agent_node)
    workflow.set_entry_point("market_analyst")
    workflow.add_conditional_edges("market_analyst", _route_after_market_analyst, {"signal_agent": "signal_agent", END: END})
    workflow.add_conditional_edges("signal_agent", _route_after_signal_agent, {"risk_engine": "risk_engine", END: END})
    workflow.add_conditional_edges("risk_engine", _route_after_risk_engine, {"approval_gate": "approval_gate", END: END})
    workflow.add_conditional_edges("approval_gate", _route_after_approval_gate, {"execution_agent": "execution_agent", END: END})
    workflow.add_edge("execution_agent", "portfolio_agent")
    workflow.add_edge("portfolio_agent", END)
    return workflow.compile(checkpointer=checkpointer)


def get_trading_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_trading_graph(checkpointer=RedisCheckpointer())
    return _graph_instance


def reset_graph() -> None:
    global _graph_instance
    _graph_instance = None


async def run_trading_cycle(tick: dict) -> dict:
    initial_state = {
        "symbol": tick["symbol"],
        "mode": settings.trading_mode,
        "cycle_id": str(uuid.uuid4()),
        "tick": tick,
        "errors": [],
        "node_timings": {},
    }
    graph = get_trading_graph()
    return await graph.ainvoke(initial_state, config={"configurable": {"thread_id": tick["symbol"]}})
