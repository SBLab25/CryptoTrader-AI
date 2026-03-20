# File: src/agents/orchestrator.py
"""
Orchestrator Agent
Master coordinator that runs the full trading cycle:
1. Fetch market data (Market Analyst)
2. Generate signals (Signal Agent)
3. Validate risk (Risk Manager)
4. Execute trades (Execution Agent)
5. Track portfolio (Portfolio Agent)

Runs every SCAN_INTERVAL_SECONDS continuously.
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Callable

from src.agents.market_analyst import MarketAnalystAgent
from src.agents.signal_agent import generate_signals_batch
from src.agents.portfolio_agent import PortfolioAgent
from src.agents.execution_agent import ExecutionAgent
from src.core.models import Trade, TradeSignal, OrderSide, OrderStatus, AgentState, SignalStrength
from src.exchange.paper_engine import PaperTradingEngine, MockExchangeClient
from src.risk.engine import risk_engine
from src.notifications.telegram import notifier
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradingOrchestrator:
    """
    Central coordinator for all trading agents.
    Implements a continuous trading loop with full state management.
    """

    def __init__(self):
        self.symbols = settings.symbol_list
        self.scan_interval = settings.scan_interval_seconds
        self.is_running = False

        # Initialize sub-agents
        self.market_analyst = MarketAnalystAgent()
        self.portfolio_agent = PortfolioAgent()

        # Paper trading engine
        self.paper_engine = PaperTradingEngine(settings.initial_capital)
        self.exchange_client = MockExchangeClient(self.paper_engine)
        self.execution_agent = ExecutionAgent(self.paper_engine)

        # Event callbacks (for WebSocket broadcasting)
        self._on_signal: Optional[Callable] = None
        self._on_trade: Optional[Callable] = None
        self._on_portfolio_update: Optional[Callable] = None

        # Cycle tracking
        self._cycle_count = 0
        self._last_cycle_at: Optional[datetime] = None

        # Active signals (prevent duplicate trades)
        self._active_symbols: set = set()

    def on_signal(self, callback: Callable):
        self._on_signal = callback

    def on_trade(self, callback: Callable):
        self._on_trade = callback

    def on_portfolio_update(self, callback: Callable):
        self._on_portfolio_update = callback

    async def start(self):
        """Start the trading loop"""
        logger.info("=" * 60)
        logger.info("🚀 Trading Orchestrator Starting")
        logger.info(f"   Mode: {'📄 PAPER TRADING' if not settings.is_live_trading else '💰 LIVE TRADING'}")
        logger.info(f"   Symbols: {', '.join(self.symbols)}")
        logger.info(f"   Scan Interval: {self.scan_interval}s")
        logger.info(f"   Max Positions: {settings.max_open_positions}")
        logger.info(f"   Max Position Size: {settings.max_position_size_pct}%")
        logger.info("=" * 60)

        self.is_running = True
        await self.market_analyst.start()

        await notifier.alert_system_start(settings.trading_mode, self.symbols)

        try:
            while self.is_running:
                try:
                    await self._run_cycle()
                except Exception as e:
                    logger.error(f"[ORCHESTRATOR] Cycle error: {e}", exc_info=True)

                await asyncio.sleep(self.scan_interval)
        finally:
            await self.market_analyst.stop()

    async def stop(self):
        """Gracefully stop the trading loop"""
        logger.info("[ORCHESTRATOR] Stopping trading loop...")
        self.is_running = False

    async def _run_cycle(self):
        """Single trading cycle"""
        self._cycle_count += 1
        self._last_cycle_at = datetime.utcnow()
        cycle_id = f"cycle-{self._cycle_count}"

        logger.info(f"\n{'─'*50}")
        logger.info(f"[{cycle_id}] Starting market scan...")

        # STEP 1: Fetch market data
        market_data_map, ohlcv_map = await self.market_analyst.fetch_all_symbols(self.symbols)

        if not market_data_map:
            logger.warning(f"[{cycle_id}] No market data available, skipping cycle")
            return

        # STEP 2: Update paper engine with latest prices
        current_prices = {s: md.price for s, md in market_data_map.items()}
        for symbol, price in current_prices.items():
            self.exchange_client.update_price(symbol, price)

        # STEP 3: Check stop-loss / take-profit on open positions
        triggered = self.paper_engine.check_stop_take_profit(current_prices)
        for trigger in triggered:
            trade = self._find_open_trade_by_order_id(trigger.get("order_id", ""))
            if trade:
                self.portfolio_agent.record_trade_closed(
                    trade,
                    trigger.get("exit_price", trade.entry_price),
                    trigger.get("trigger", "unknown"),
                )
                self._active_symbols.discard(trade.symbol)
                if self._on_trade:
                    await self._on_trade(trade)
                risk_engine.update_daily_pnl(trade.pnl or 0)

        # STEP 4: Get portfolio snapshot
        portfolio = self.portfolio_agent.get_portfolio_snapshot(current_prices)
        if self._on_portfolio_update:
            await self._on_portfolio_update(portfolio)

        logger.info(
            f"[{cycle_id}] Portfolio: ${portfolio.total_value:,.2f} | "
            f"Cash: ${portfolio.available_balance:,.2f} | "
            f"Open: {portfolio.open_positions.__len__()} positions | "
            f"PnL: {portfolio.total_pnl:+.2f} ({portfolio.total_pnl_pct:+.2f}%)"
        )

        # STEP 5: Skip signal generation if risk paused
        if risk_engine.is_paused:
            logger.warning(f"[{cycle_id}] Trading PAUSED by risk engine — skipping signal generation")
            return

        # STEP 6: Filter out symbols already in active trades
        scan_symbols_data = {
            s: md for s, md in market_data_map.items()
            if s not in self._active_symbols
        }
        scan_ohlcv = {
            s: ohlcv for s, ohlcv in ohlcv_map.items()
            if s not in self._active_symbols
        }

        if not scan_symbols_data:
            logger.info(f"[{cycle_id}] All symbols have active trades — waiting")
            return

        # STEP 7: Generate AI + TA signals
        signals: List[TradeSignal] = await generate_signals_batch(
            scan_symbols_data, scan_ohlcv
        )

        logger.info(f"[{cycle_id}] Generated {len(signals)} actionable signals")

        for signal in signals:
            if self._on_signal:
                await self._on_signal(signal)

        # STEP 8: Risk assessment and trade execution
        for signal in signals:
            if self.portfolio_agent.open_trade_count >= settings.max_open_positions:
                logger.info(f"[{cycle_id}] Max positions reached — no more trades this cycle")
                break

            risk_result = risk_engine.assess_trade(
                signal,
                portfolio,
                self.portfolio_agent.open_trade_count,
            )

            if not risk_result.approved:
                logger.info(f"[{cycle_id}] {signal.symbol} rejected: {risk_result.reason}")
                continue

            # STEP 9: Execute trade
            side = (
                OrderSide.BUY
                if signal.signal in [SignalStrength.BUY, SignalStrength.STRONG_BUY]
                else OrderSide.SELL
            )

            order_result = await self.exchange_client.place_order(
                symbol=signal.symbol,
                side=side.value,
                quantity=risk_result.trade_size,
                price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )

            if "error" in order_result:
                logger.error(f"[{cycle_id}] Order failed for {signal.symbol}: {order_result['error']}")
                continue

            # Record trade
            trade = Trade(
                symbol=signal.symbol,
                side=side,
                quantity=risk_result.trade_size,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                status=OrderStatus.OPEN,
                exchange_order_id=order_result.get("order_id"),
                strategy="ai_driven",
                signal_id=signal.id,
                is_paper=not settings.is_live_trading,
            )

            cost = risk_result.trade_size * signal.entry_price
            self.portfolio_agent.record_trade_opened(trade, cost)
            self._active_symbols.add(signal.symbol)
            self._store_trade(trade)

            if self._on_trade:
                await self._on_trade(trade)

            logger.info(
                f"[{cycle_id}] ✅ Trade placed: {signal.symbol} {side.value.upper()} "
                f"{risk_result.trade_size:.6f} @ {signal.entry_price} | "
                f"SL: {signal.stop_loss} | TP: {signal.take_profit}"
            )

        logger.info(f"[{cycle_id}] Cycle complete ✓")

    # --- Internal helpers ---

    _open_trade_map: Dict[str, Trade] = {}  # order_id -> Trade

    def _store_trade(self, trade: Trade):
        if trade.exchange_order_id:
            self._open_trade_map[trade.exchange_order_id] = trade

    def _find_open_trade_by_order_id(self, order_id: str) -> Optional[Trade]:
        return self._open_trade_map.get(order_id)

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "cycle_count": self._cycle_count,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "symbols": self.symbols,
            "active_symbols": list(self._active_symbols),
            "open_positions": self.portfolio_agent.open_trade_count,
            "trading_paused": risk_engine.is_paused,
            "mode": "paper" if not settings.is_live_trading else "live",
            "performance": self.portfolio_agent.get_performance_stats(),
        }
