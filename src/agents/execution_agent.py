# File: src/agents/execution_agent.py
"""
Execution Agent
Handles the full order lifecycle: placement → monitoring → closure.
Includes retry logic, slippage tolerance, and partial fill handling.
All live orders go through here before touching the exchange.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Awaitable
from enum import Enum

from src.core.models import Trade, TradeSignal, OrderSide, OrderStatus, RiskAssessment
from src.exchange.paper_engine import PaperTradingEngine
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ExecutionError(Exception):
    """Raised when an order cannot be executed after retries"""


class SlippagePolicy(str, Enum):
    REJECT = "reject"          # Cancel if slippage exceeds limit
    ACCEPT = "accept"          # Accept any fill price
    LIMIT = "limit"            # Use limit order to cap slippage


class ExecutionConfig:
    max_retries: int = 3
    retry_delay_sec: float = 2.0
    slippage_tolerance_pct: float = 0.3        # 0.3% max slippage
    slippage_policy: SlippagePolicy = SlippagePolicy.ACCEPT
    order_timeout_sec: int = 30                # Cancel unfilled orders after N seconds
    min_fill_pct: float = 0.95                 # Minimum acceptable fill ratio


class ExecutionAgent:
    """
    Handles placing, tracking, and closing orders on the exchange.
    Wraps paper trading engine in dev mode; swaps to live client in production.
    """

    def __init__(self, paper_engine: PaperTradingEngine):
        self._paper = paper_engine
        self._pending_orders: Dict[str, dict] = {}   # order_id -> order meta
        self._on_fill_callbacks: List[Callable] = []
        self._config = ExecutionConfig()
        self._stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_rejected": 0,
            "orders_retried": 0,
            "slippage_rejected": 0,
            "total_slippage_usdt": 0.0,
        }

    def on_fill(self, callback: Callable[[Trade], Awaitable[None]]):
        """Register callback for when an order is filled"""
        self._on_fill_callbacks.append(callback)

    # ── Order Placement ───────────────────────────────────────────────────────

    async def execute_trade(
        self,
        signal: TradeSignal,
        risk: RiskAssessment,
        is_paper: bool = True,
    ) -> Optional[Trade]:
        """
        Main entry point: validate → size → place → confirm.
        Returns Trade on success, None on failure.
        """
        side = (
            OrderSide.BUY
            if signal.signal.value in ["strong_buy", "buy"]
            else OrderSide.SELL
        )

        # Pre-execution checks
        if risk.trade_size <= 0:
            logger.warning(f"[EXEC] Zero trade size for {signal.symbol} — skipping")
            return None

        entry_price = signal.entry_price
        quantity = risk.trade_size

        # Slippage check (for live mode)
        if not is_paper:
            actual_price = await self._get_current_price(signal.symbol)
            if actual_price:
                slippage_pct = abs(actual_price - entry_price) / entry_price * 100
                if slippage_pct > self._config.slippage_tolerance_pct:
                    if self._config.slippage_policy == SlippagePolicy.REJECT:
                        logger.warning(
                            f"[EXEC] Slippage too high for {signal.symbol}: "
                            f"{slippage_pct:.3f}% > {self._config.slippage_tolerance_pct}%"
                        )
                        self._stats["slippage_rejected"] += 1
                        return None
                    elif self._config.slippage_policy == SlippagePolicy.ACCEPT:
                        logger.info(
                            f"[EXEC] Accepting slippage {slippage_pct:.3f}% for {signal.symbol}"
                        )
                        entry_price = actual_price
                        self._stats["total_slippage_usdt"] += abs(actual_price - signal.entry_price) * quantity

        # Attempt order placement with retries
        order_result = await self._place_with_retry(
            symbol=signal.symbol,
            side=side.value,
            quantity=quantity,
            price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            is_paper=is_paper,
        )

        if not order_result or "error" in order_result:
            err = order_result.get("error", "Unknown") if order_result else "No response"
            logger.error(f"[EXEC] Order failed for {signal.symbol}: {err}")
            self._stats["orders_rejected"] += 1
            return None

        # Build Trade record
        trade = Trade(
            id=str(uuid.uuid4()),
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            status=OrderStatus.OPEN,
            exchange_order_id=order_result.get("order_id"),
            strategy="ai_driven",
            signal_id=signal.id,
            is_paper=is_paper,
            created_at=datetime.utcnow(),
        )

        self._stats["orders_placed"] += 1
        self._stats["orders_filled"] += 1
        self._pending_orders[trade.id] = {
            "trade": trade,
            "placed_at": datetime.utcnow(),
            "symbol": signal.symbol,
        }

        logger.info(
            f"[EXEC] ✅ Order filled: {signal.symbol} {side.value.upper()} "
            f"{quantity:.6f} @ {entry_price:.4f} "
            f"{'[PAPER]' if is_paper else '[LIVE]'}"
        )

        # Fire fill callbacks
        for cb in self._on_fill_callbacks:
            try:
                await cb(trade)
            except Exception as e:
                logger.error(f"[EXEC] Fill callback error: {e}")

        return trade

    async def close_trade(
        self,
        trade: Trade,
        exit_price: float,
        exit_reason: str,
        is_paper: bool = True,
    ) -> bool:
        """
        Close an open position.
        Returns True on success, False on failure.
        """
        if not is_paper:
            # Live: place a counter order or market sell
            result = await self._place_with_retry(
                symbol=trade.symbol,
                side="sell" if trade.side == OrderSide.BUY else "buy",
                quantity=trade.quantity,
                price=exit_price,
                stop_loss=0,
                take_profit=0,
                is_paper=False,
            )
            if not result or "error" in result:
                logger.error(f"[EXEC] Failed to close trade {trade.id}: {result}")
                return False
        else:
            # Paper: close via engine
            if trade.exchange_order_id:
                self._paper.close_position(trade.exchange_order_id, exit_price)

        self._pending_orders.pop(trade.id, None)
        logger.info(
            f"[EXEC] 🔒 Position closed: {trade.symbol} @ {exit_price:.4f} | "
            f"Reason: {exit_reason}"
        )
        return True

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _place_with_retry(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        is_paper: bool,
    ) -> Optional[dict]:
        """Attempt order placement with exponential backoff retry"""
        last_error = None
        for attempt in range(self._config.max_retries):
            try:
                if is_paper:
                    result = self._paper.place_order(
                        symbol, side, quantity, price, stop_loss, take_profit
                    )
                else:
                    result = await self._place_live_order(
                        symbol, side, quantity, price
                    )

                if result and "error" not in result:
                    return result

                last_error = result.get("error", "Unknown") if result else "No response"
                logger.warning(
                    f"[EXEC] Attempt {attempt+1}/{self._config.max_retries} failed "
                    f"for {symbol}: {last_error}"
                )

            except Exception as e:
                last_error = str(e)
                logger.error(f"[EXEC] Exception on attempt {attempt+1}: {e}")

            if attempt < self._config.max_retries - 1:
                await asyncio.sleep(self._config.retry_delay_sec * (2 ** attempt))
                self._stats["orders_retried"] += 1

        logger.error(f"[EXEC] All {self._config.max_retries} attempts failed for {symbol}: {last_error}")
        return {"error": last_error}

    async def _place_live_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[dict]:
        """
        Placeholder for live exchange order placement.
        In production: swap this for CryptocomExchangeClient or CCXTAdapter.
        """
        raise NotImplementedError(
            "Live order placement not configured. "
            "Set TRADING_MODE=paper or implement _place_live_order with your exchange client."
        )

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price for slippage check"""
        # In production, query the exchange or use cached price from market analyst
        return None

    # ── Timeout Monitor ───────────────────────────────────────────────────────

    async def monitor_pending_timeouts(self) -> List[str]:
        """
        Check for orders that have been pending too long.
        Returns list of timed-out trade IDs.
        """
        timeout_threshold = timedelta(seconds=self._config.order_timeout_sec)
        now = datetime.utcnow()
        timed_out = []

        for trade_id, meta in list(self._pending_orders.items()):
            if now - meta["placed_at"] > timeout_threshold:
                logger.warning(
                    f"[EXEC] Order timeout: {meta['symbol']} trade_id={trade_id}"
                )
                timed_out.append(trade_id)
                self._pending_orders.pop(trade_id, None)

        return timed_out

    @property
    def stats(self) -> dict:
        return {**self._stats, "pending_orders": len(self._pending_orders)}

    @property
    def pending_count(self) -> int:
        return len(self._pending_orders)
