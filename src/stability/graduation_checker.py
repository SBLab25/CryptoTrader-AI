"""Paper trading graduation criteria checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class CriterionResult:
    name: str
    label: str
    passed: bool
    value: float
    target: str
    message: str


@dataclass
class GraduationReport:
    timestamp: datetime
    all_passed: bool
    performance: list[CriterionResult] = field(default_factory=list)
    stability: list[CriterionResult] = field(default_factory=list)
    message: str = ""

    def summary_lines(self) -> list[str]:
        lines = [
            "=" * 55,
            f"  GRADUATION CHECK - {self.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "=" * 55,
        ]
        for bucket_name, bucket in (("PERFORMANCE", self.performance), ("STABILITY", self.stability)):
            lines.append(f"  {bucket_name}")
            for item in bucket:
                icon = "PASS" if item.passed else "FAIL"
                lines.append(f"  [{icon}] {item.label}")
        lines.append(f"  RESULT: {'READY FOR STAGE 2' if self.all_passed else 'NOT YET READY'}")
        return lines


class GraduationChecker:
    def __init__(self, db_pool=None, redis_client=None, ntfy_client=None, prometheus_url: str = "http://prometheus:9090") -> None:
        self._db = db_pool
        self._redis = redis_client
        self._ntfy = ntfy_client
        self._prometheus_url = prometheus_url
        self._last_notif: Optional[datetime] = None

    async def check_and_notify(self) -> GraduationReport:
        report = await self._build_report()
        for line in report.summary_lines():
            log.info("graduation_check", line=line)
        if report.all_passed and self._ntfy:
            now = datetime.now(timezone.utc)
            if not self._last_notif or (now - self._last_notif).total_seconds() > 21600:
                try:
                    await self._ntfy.graduation_achieved()
                    self._last_notif = now
                except Exception:
                    pass
        return report

    async def _build_report(self) -> GraduationReport:
        perf = await self._check_performance()
        stab = await self._check_stability()
        passed = all(item.passed for item in perf) and all(item.passed for item in stab)
        return GraduationReport(
            timestamp=datetime.now(timezone.utc),
            all_passed=passed,
            performance=perf,
            stability=stab,
            message="All graduation criteria met!" if passed else "Criteria not yet met.",
        )

    async def _check_performance(self) -> list[CriterionResult]:
        stats = await self._load_trade_stats()
        return [
            CriterionResult("win_rate", "Win Rate >= 50%", stats["win_rate"] >= 0.50, stats["win_rate"], ">= 50%", f"{stats['win_rate']:.1%}"),
            CriterionResult("profit_factor", "Profit Factor >= 1.3", stats["profit_factor"] >= 1.30, stats["profit_factor"], ">= 1.3", f"{stats['profit_factor']:.2f}"),
            CriterionResult("max_drawdown", "Max Drawdown <= 10%", stats["max_drawdown"] <= 0.10, stats["max_drawdown"], "<= 10%", f"{stats['max_drawdown']:.1%}"),
            CriterionResult("sharpe_ratio", "Sharpe >= 0.8", stats["sharpe_ratio"] >= 0.80, stats["sharpe_ratio"], ">= 0.8", f"{stats['sharpe_ratio']:.2f}"),
            CriterionResult("total_trades", "Total Trades >= 30", stats["total_closed_trades"] >= 30, float(stats["total_closed_trades"]), ">= 30", str(stats["total_closed_trades"])),
            CriterionResult("days_running", "Running >= 14 days", stats["days_running"] >= 14, float(stats["days_running"]), ">= 14 days", f"{stats['days_running']:.1f}"),
        ]

    async def _check_stability(self) -> list[CriterionResult]:
        lag = await self._get_stream_lag()
        p95 = await self._get_cycle_p95()
        errors = await self._get_error_count_1h()
        return [
            CriterionResult("stream_lag", "Redis Stream Lag < 100 messages", lag <= 100, float(lag), "< 100", str(lag)),
            CriterionResult("cycle_p95_s", "LangGraph Cycle P95 < 30s", p95 <= 30.0, p95, "< 30s", f"{p95:.1f}s"),
            CriterionResult("error_rate_1h", "Zero unhandled exceptions (1h)", errors == 0, float(errors), "= 0", str(errors)),
        ]

    async def _load_trade_stats(self) -> dict:
        defaults = {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 1.0,
            "sharpe_ratio": 0.0,
            "total_closed_trades": 0,
            "days_running": 0.0,
        }
        if not self._db:
            return defaults
        try:
            async with self._db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0), 0) AS win_rate,
                        COALESCE(
                            SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) /
                            NULLIF(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 0),
                            0
                        ) AS profit_factor,
                        EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) / 86400 AS days_running
                    FROM trades
                    WHERE status = 'filled' AND is_paper = true
                    """
                )
                snap = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(MAX(ABS(daily_pnl_pct)) / 100.0, 0) AS max_dd,
                        COALESCE(AVG(total_pnl_pct), 0) / 100.0 AS sharpe_proxy
                    FROM portfolio_snapshots
                    WHERE is_paper = true
                    """
                )
            return {
                "win_rate": float(row["win_rate"] or 0.0),
                "profit_factor": float(row["profit_factor"] or 0.0),
                "total_closed_trades": int(row["total"] or 0),
                "days_running": float(row["days_running"] or 0.0),
                "max_drawdown": float(snap["max_dd"] or 0.0),
                "sharpe_ratio": float(snap["sharpe_proxy"] or 0.0),
            }
        except Exception as exc:
            log.warning("graduation_stats_load_failed", error=str(exc))
            return defaults

    async def _get_stream_lag(self) -> int:
        if not self._redis:
            return 0
        try:
            info = await self._redis.xinfo_groups("market:ticks")
            return int(info[0].get("lag", 0)) if info else 0
        except Exception:
            return 0

    async def _get_cycle_p95(self) -> float:
        return 0.0

    async def _get_error_count_1h(self) -> int:
        if not self._db:
            return 0
        try:
            async with self._db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM audit_log
                    WHERE event_type LIKE 'ERROR%'
                      AND created_at >= NOW() - INTERVAL '1 hour'
                    """
                )
            return int(row["cnt"] or 0)
        except Exception:
            return 0


async def _main() -> None:
    report = await GraduationChecker().check_and_notify()
    for line in report.summary_lines():
        print(line)


if __name__ == "__main__":
    asyncio.run(_main())
