# File: src/agents/portfolio_agent.py
"""
Portfolio Agent
Tracks open positions, realized/unrealized PnL, and performance metrics.
"""
from typing import Dict, List, Optional
from datetime import datetime, date

from src.core.models import Trade, Position, Portfolio, OrderSide, OrderStatus
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PortfolioAgent:
    def __init__(self, initial_capital: float = None):
        self._initial_capital = initial_capital or settings.initial_capital
        self._cash_balance = self._initial_capital
        self._open_trades: Dict[str, Trade] = {}  # trade_id -> Trade
        self._closed_trades: List[Trade] = []
        self._daily_pnl_start = self._initial_capital
        self._peak_value = self._initial_capital

    def record_trade_opened(self, trade: Trade, cost: float):
        """Record a newly opened trade and deduct cost from balance"""
        self._open_trades[trade.id] = trade
        self._cash_balance -= cost
        logger.info(
            f"[PORTFOLIO] Opened trade {trade.id} | {trade.symbol} {trade.side.value} "
            f"{trade.quantity:.6f} @ {trade.entry_price} | Cost: ${cost:.2f}"
        )

    def record_trade_closed(self, trade: Trade, exit_price: float, exit_reason: str):
        """Close a trade and update balances"""
        if trade.id not in self._open_trades:
            logger.warning(f"[PORTFOLIO] Trade {trade.id} not found in open trades")
            return

        trade.exit_price = exit_price
        trade.closed_at = datetime.utcnow()
        trade.exit_reason = exit_reason
        trade.status = OrderStatus.FILLED

        if trade.side == OrderSide.BUY:
            proceeds = trade.quantity * exit_price
            cost = trade.quantity * trade.entry_price
            trade.pnl = proceeds - cost
        else:
            proceeds = trade.quantity * trade.entry_price
            cost = trade.quantity * exit_price
            trade.pnl = proceeds - cost

        trade.pnl_pct = (trade.pnl / (trade.quantity * trade.entry_price)) * 100
        self._cash_balance += (trade.quantity * exit_price)

        del self._open_trades[trade.id]
        self._closed_trades.append(trade)

        emoji = "✅" if trade.pnl >= 0 else "❌"
        logger.info(
            f"[PORTFOLIO] {emoji} Closed {trade.id} | {trade.symbol} | "
            f"Exit: {exit_price} | PnL: {trade.pnl:+.4f} USDT ({trade.pnl_pct:+.2f}%) | "
            f"Reason: {exit_reason}"
        )

    def get_portfolio_snapshot(self, current_prices: Dict[str, float]) -> Portfolio:
        """Compute current portfolio state with live prices"""
        positions = []
        total_unrealized_pnl = 0.0

        for trade in self._open_trades.values():
            current_price = current_prices.get(trade.symbol, trade.entry_price)
            
            if trade.side == OrderSide.BUY:
                unrealized = (current_price - trade.entry_price) * trade.quantity
            else:
                unrealized = (trade.entry_price - current_price) * trade.quantity

            unrealized_pct = (unrealized / (trade.entry_price * trade.quantity)) * 100
            total_unrealized_pnl += unrealized

            positions.append(Position(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                entry_price=trade.entry_price,
                current_price=current_price,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                trade_id=trade.id,
                unrealized_pnl=round(unrealized, 4),
                unrealized_pnl_pct=round(unrealized_pct, 2),
                opened_at=trade.created_at,
            ))

        # Compute totals
        invested_value = sum(
            t.quantity * current_prices.get(t.symbol, t.entry_price)
            for t in self._open_trades.values()
        )
        total_value = self._cash_balance + invested_value

        realized_pnl = sum(t.pnl or 0 for t in self._closed_trades)
        total_pnl = realized_pnl + total_unrealized_pnl
        total_pnl_pct = (total_pnl / self._initial_capital) * 100

        daily_pnl = total_value - self._daily_pnl_start
        daily_pnl_pct = (daily_pnl / self._daily_pnl_start) * 100

        # Update peak
        if total_value > self._peak_value:
            self._peak_value = total_value

        return Portfolio(
            total_value=round(total_value, 4),
            available_balance=round(self._cash_balance, 4),
            invested_value=round(invested_value, 4),
            total_pnl=round(total_pnl, 4),
            total_pnl_pct=round(total_pnl_pct, 2),
            daily_pnl=round(daily_pnl, 4),
            daily_pnl_pct=round(daily_pnl_pct, 2),
            open_positions=positions,
            is_paper=not settings.is_live_trading,
        )

    def reset_daily_tracking(self, current_portfolio_value: float):
        """Call at midnight to reset daily PnL tracking"""
        self._daily_pnl_start = current_portfolio_value

    @property
    def open_trade_count(self) -> int:
        return len(self._open_trades)

    @property
    def total_trades(self) -> int:
        return len(self._closed_trades)

    @property
    def win_rate(self) -> float:
        if not self._closed_trades:
            return 0.0
        wins = sum(1 for t in self._closed_trades if (t.pnl or 0) > 0)
        return round(wins / len(self._closed_trades) * 100, 2)

    def get_performance_stats(self) -> dict:
        if not self._closed_trades:
            return {"message": "No closed trades yet"}

        pnls = [t.pnl or 0 for t in self._closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        return {
            "total_trades": len(self._closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": self.win_rate,
            "total_pnl": round(sum(pnls), 4),
            "avg_win": round(sum(wins) / len(wins), 4) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else float("inf"),
            "max_win": round(max(pnls), 4),
            "max_loss": round(min(pnls), 4),
            "peak_portfolio": round(self._peak_value, 4),
        }
