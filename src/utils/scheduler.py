# File: src/utils/scheduler.py
"""
Daily Scheduler
Handles time-based tasks:
  - Daily PnL reset at UTC midnight
  - Daily performance summary notification
  - Stale position alerts
  - Risk engine daily reset
  - Portfolio snapshot archival
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from typing import Optional, Callable, Awaitable, List
from dataclasses import dataclass, field

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScheduledTask:
    name: str
    hour: int
    minute: int
    callback: Callable[[], Awaitable[None]]
    last_run: Optional[datetime] = None
    run_count: int = 0
    errors: List[str] = field(default_factory=list)

    def is_due(self, now: datetime) -> bool:
        """True if this task should fire right now (within the current minute)"""
        if now.hour != self.hour or now.minute != self.minute:
            return False
        # Prevent double-firing within the same minute
        if self.last_run and (now - self.last_run).total_seconds() < 60:
            return False
        return True


class DailyScheduler:
    """
    Lightweight async scheduler that runs tasks at specific UTC times.
    Runs as a background asyncio task alongside the main trading loop.
    """

    def __init__(self):
        self._tasks: List[ScheduledTask] = []
        self._is_running = False
        self._tick_interval = 30    # Check every 30 seconds

    def register(self, name: str, hour: int, minute: int, callback: Callable):
        """Register a UTC-time daily task"""
        task = ScheduledTask(name=name, hour=hour, minute=minute, callback=callback)
        self._tasks.append(task)
        logger.info(f"[SCHEDULER] Registered: '{name}' at {hour:02d}:{minute:02d} UTC")

    async def start(self):
        """Start the scheduler loop"""
        self._is_running = True
        logger.info("[SCHEDULER] Daily scheduler started")
        while self._is_running:
            await self._tick()
            await asyncio.sleep(self._tick_interval)

    async def stop(self):
        self._is_running = False
        logger.info("[SCHEDULER] Scheduler stopped")

    async def _tick(self):
        now = datetime.utcnow()
        for task in self._tasks:
            if task.is_due(now):
                logger.info(f"[SCHEDULER] Running: '{task.name}'")
                try:
                    await task.callback()
                    task.last_run = now
                    task.run_count += 1
                    logger.info(f"[SCHEDULER] ✅ '{task.name}' completed (run #{task.run_count})")
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                    task.errors.append(err)
                    logger.error(f"[SCHEDULER] ❌ '{task.name}' failed: {err}")

    def get_status(self) -> list:
        return [
            {
                "name": t.name,
                "scheduled_utc": f"{t.hour:02d}:{t.minute:02d}",
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "run_count": t.run_count,
                "error_count": len(t.errors),
            }
            for t in self._tasks
        ]


def build_scheduler(
    portfolio_agent,
    risk_engine,
    notifier,
    ws_broadcast_fn: Optional[Callable] = None,
) -> DailyScheduler:
    """
    Factory: create and configure the scheduler with all standard tasks.

    Tasks registered:
      00:00  - Midnight reset (daily PnL, risk limits)
      00:01  - Send daily summary via Telegram
      00:05  - Archive portfolio snapshot
      08:00  - Morning market scan alert
      20:00  - Evening summary
    """
    scheduler = DailyScheduler()

    # ── Task: Midnight PnL Reset ──────────────────────────────────────────────
    async def midnight_reset():
        logger.info("[SCHEDULER] 🌙 Midnight reset: resetting daily PnL tracking")

        # Get current portfolio value for reset baseline
        # (prices may be stale at midnight but good enough for daily tracking)
        try:
            snapshot = portfolio_agent.get_portfolio_snapshot({})
            portfolio_agent.reset_daily_tracking(snapshot.total_value)
            risk_engine.reset_daily_pnl()
            logger.info(
                f"[SCHEDULER] Daily PnL reset. New baseline: ${snapshot.total_value:,.2f}"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER] Midnight reset error: {e}")

    scheduler.register("Midnight PnL Reset", hour=0, minute=0, callback=midnight_reset)

    # ── Task: Daily Summary ───────────────────────────────────────────────────
    async def daily_summary():
        logger.info("[SCHEDULER] 📊 Sending daily summary")
        try:
            snapshot = portfolio_agent.get_portfolio_snapshot({})
            stats = portfolio_agent.get_performance_stats()
            await notifier.alert_daily_summary(snapshot, stats)

            if ws_broadcast_fn:
                await ws_broadcast_fn({
                    "type": "daily_summary",
                    "data": {
                        "portfolio": snapshot.model_dump(mode="json"),
                        "stats": stats,
                    }
                })
        except Exception as e:
            logger.error(f"[SCHEDULER] Daily summary error: {e}")

    scheduler.register("Daily Summary", hour=0, minute=1, callback=daily_summary)

    # ── Task: Stale Position Alert ────────────────────────────────────────────
    async def stale_position_check():
        """Alert if a position has been open for more than 24h"""
        try:
            snapshot = portfolio_agent.get_portfolio_snapshot({})
            now = datetime.utcnow()
            stale_threshold = timedelta(hours=24)

            for pos in snapshot.open_positions:
                age = now - pos.opened_at
                if age > stale_threshold:
                    hours = int(age.total_seconds() // 3600)
                    msg = (
                        f"⏰ <b>Stale Position Alert</b>\n\n"
                        f"Symbol: <code>{pos.symbol}</code>\n"
                        f"Side: <code>{pos.side.value.upper()}</code>\n"
                        f"Open for: <code>{hours}h</code>\n"
                        f"Unrealised PnL: <code>${pos.unrealized_pnl:+.4f}</code>\n\n"
                        f"Consider reviewing this position."
                    )
                    await notifier.send(msg)
                    logger.warning(f"[SCHEDULER] Stale position: {pos.symbol} open {hours}h")
        except Exception as e:
            logger.error(f"[SCHEDULER] Stale position check error: {e}")

    scheduler.register("Stale Position Check", hour=12, minute=0, callback=stale_position_check)

    # ── Task: Evening Summary ─────────────────────────────────────────────────
    async def evening_check():
        """Mid-day portfolio health check"""
        try:
            snapshot = portfolio_agent.get_portfolio_snapshot({})
            stats = portfolio_agent.get_performance_stats()

            # Only send if there's been activity today
            if stats.get("total_trades", 0) > 0:
                await notifier.alert_daily_summary(snapshot, stats)
                logger.info("[SCHEDULER] Evening summary sent")
        except Exception as e:
            logger.error(f"[SCHEDULER] Evening check error: {e}")

    scheduler.register("Evening Summary", hour=20, minute=0, callback=evening_check)

    return scheduler
