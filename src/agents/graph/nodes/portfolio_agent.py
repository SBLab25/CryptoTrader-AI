"""Phase 3 portfolio node."""

from __future__ import annotations

import time

from src.agents.graph.runtime import portfolio_agent
from src.db.redis_client import broadcast


async def portfolio_agent_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        price = float(state["tick"]["close"])
        portfolio = portfolio_agent.get_portfolio_snapshot({state["symbol"]: price})
        payload = portfolio.model_dump(mode="json")
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
