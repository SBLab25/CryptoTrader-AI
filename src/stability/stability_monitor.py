"""Hourly stability monitor checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class StabilityIssue:
    severity: str
    name: str
    message: str
    fix: str = ""


@dataclass
class StabilityReport:
    timestamp: datetime
    issues: list[StabilityIssue] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(issue.severity == "critical" for issue in self.issues)

    @property
    def is_healthy(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        if self.is_healthy:
            return "All stability checks passed"
        return "\n".join(f"[{issue.severity.upper()}] {issue.name}: {issue.message}" for issue in self.issues)


class StabilityMonitor:
    SIGNAL_GAP_HOURS = 2.0

    def __init__(self, db_pool=None, redis_client=None, signal_memory=None, ntfy_client=None) -> None:
        self._db = db_pool
        self._redis = redis_client
        self._memory = signal_memory
        self._ntfy = ntfy_client

    async def run_hourly_check(self) -> StabilityReport:
        issues: list[StabilityIssue] = []
        for result in await asyncio.gather(
            self._check_signal_gap(),
            self._check_qdrant_outcome_lag(),
            self._check_orphaned_positions(),
            self._check_redis_stream_health(),
            return_exceptions=True,
        ):
            if isinstance(result, Exception):
                log.warning("stability_check_exception", error=str(result))
            elif result is not None:
                issues.append(result)
        report = StabilityReport(timestamp=datetime.now(timezone.utc), issues=issues)
        if issues and self._ntfy:
            try:
                await self._ntfy.send(
                    title="CryptoTrader-AI Stability Alert",
                    message=report.summary(),
                    priority=5 if report.has_critical else 3,
                )
            except Exception:
                pass
        return report

    async def _check_signal_gap(self) -> Optional[StabilityIssue]:
        if not self._db:
            return None
        try:
            async with self._db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT MAX(timestamp) AS last_signal
                    FROM signals
                    """
                )
            if not row or not row["last_signal"]:
                return StabilityIssue("warning", "no_signals_ever", "No signals found in database")
            return None
        except Exception as exc:
            log.warning("signal_gap_check_failed", error=str(exc))
            return None

    async def _check_qdrant_outcome_lag(self) -> Optional[StabilityIssue]:
        if not self._db or not self._memory:
            return None
        try:
            async with self._db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM trades
                    WHERE status = 'filled'
                      AND signal_id IS NOT NULL
                      AND closed_at >= NOW() - INTERVAL '4 hours'
                    """
                )
            closed_recently = int(row["cnt"] or 0)
            if closed_recently == 0:
                return None
            stats_fn = getattr(self._memory, "collection_stats", None)
            if stats_fn is None:
                return StabilityIssue("warning", "qdrant_stats_missing", "Signal memory stats unavailable")
            stats = stats_fn()
            if hasattr(stats, "__await__"):
                stats = await stats
            if not stats.get("available", False):
                return StabilityIssue("warning", "qdrant_unavailable", "Qdrant is not reachable")
        except Exception as exc:
            log.warning("qdrant_outcome_check_failed", error=str(exc))
        return None

    async def _check_orphaned_positions(self) -> Optional[StabilityIssue]:
        if not self._db:
            return None
        try:
            async with self._db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM trades
                    WHERE status = 'open'
                      AND (stop_loss IS NULL OR take_profit IS NULL)
                    """
                )
            if int(row["cnt"] or 0) > 0:
                return StabilityIssue("critical", "orphaned_positions", f"{int(row['cnt'])} open position(s) with no SL/TP set")
        except Exception as exc:
            log.warning("orphan_check_failed", error=str(exc))
        return None

    async def _check_redis_stream_health(self) -> Optional[StabilityIssue]:
        if not self._redis:
            return None
        try:
            groups = await self._redis.xinfo_groups("market:ticks")
            for group in groups:
                lag = int(group.get("lag", 0))
                if lag > 1000:
                    return StabilityIssue("warning", "redis_stream_high_lag", f"market:ticks consumer lag: {lag} messages")
        except Exception as exc:
            log.warning("redis_stream_check_failed", error=str(exc))
        return None
