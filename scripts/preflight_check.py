"""Pre-live validation checks for Phase 6 hardening."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    critical: bool = False

    @property
    def icon(self) -> str:
        return {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL", "SKIP": "SKIP"}.get(self.status, "?")


class PreflightChecker:
    def __init__(self):
        self.results: list[CheckResult] = []

    def _add(self, name: str, passed: bool, detail: str = "", critical: bool = False, warn_only: bool = False):
        status = "PASS" if passed else "WARN" if warn_only else "FAIL"
        self.results.append(CheckResult(name=name, status=status, detail=detail, critical=critical))

    async def check_vault(self) -> None:
        settings = get_settings()
        if not settings.vault_addr:
            self._add("Vault: configured", False, "VAULT_ADDR not set", critical=settings.is_live_trading)
            return
        try:
            from src.core.vault import get_vault_client

            vault = get_vault_client(settings.vault_addr, settings.vault_token)
            self._add("Vault: reachable and authenticated", vault is not None, critical=settings.is_live_trading)
        except Exception as exc:
            self._add("Vault: reachable and authenticated", False, str(exc), critical=settings.is_live_trading)

    def check_jwt(self) -> None:
        settings = get_settings()
        key = settings.jwt_signing_key or ""
        self._add("JWT: key is set", bool(key), critical=True)
        self._add("JWT: key >= 32 characters", len(key) >= 32, f"Length: {len(key)}", critical=True)

    async def check_database(self) -> None:
        try:
            from src.db.database import get_db_session, init_db
            from sqlalchemy import text

            await init_db()
            async with get_db_session() as session:
                await session.execute(text("SELECT 1"))
            self._add("Database: reachable", True, critical=True)
        except Exception as exc:
            self._add("Database: reachable", False, str(exc), critical=True)

    async def check_redis(self) -> None:
        try:
            from src.db.redis_client import ping

            self._add("Redis: reachable", await ping(), critical=True)
        except Exception as exc:
            self._add("Redis: reachable", False, str(exc), critical=True)

    async def check_exchange(self) -> None:
        settings = get_settings()
        self._add(
            "Exchange: CRYPTOCOM_SANDBOX=False",
            not settings.cryptocom_sandbox,
            "Disable sandbox before going live" if settings.cryptocom_sandbox else "",
            critical=settings.is_live_trading,
        )
        has_creds = bool(settings.cryptocom_api_key and settings.cryptocom_api_secret) or bool(settings.vault_addr)
        self._add("Exchange: credentials available", has_creds, "Check Vault or env", critical=settings.is_live_trading)

    async def check_notifications(self) -> None:
        try:
            from src.notifications.ntfy import notify_test

            self._add("Ntfy: test notification sent", await notify_test(), warn_only=True)
        except Exception as exc:
            self._add("Ntfy: test notification sent", False, str(exc), warn_only=True)

    def check_qdrant(self) -> None:
        try:
            from src.memory.qdrant_client import check_qdrant_health

            self._add("Qdrant: reachable", bool(check_qdrant_health()), warn_only=True)
        except Exception as exc:
            self._add("Qdrant: reachable", False, str(exc), warn_only=True)

    async def check_paper_history(self) -> None:
        try:
            from sqlalchemy import text
            from src.db.database import get_db_session, init_db

            await init_db()
            async with get_db_session() as session:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT MIN(created_at) AS first_trade,
                                   COUNT(*) AS total
                            FROM trades
                            WHERE is_paper = 1
                            """
                        )
                    )
                ).fetchone()

            if not row or not row.first_trade:
                self._add("Paper trading: history present", False, "No paper trade history", warn_only=True)
                return

            from datetime import datetime, timezone

            days = (datetime.now(tz=timezone.utc) - row.first_trade.replace(tzinfo=timezone.utc)).days
            self._add(f"Paper trading: >= 14 days history ({days} days)", days >= 14, warn_only=True)
        except Exception as exc:
            self._add("Paper trading: history check", False, str(exc), warn_only=True)

    def check_settings(self) -> None:
        s = get_settings()
        self._add(f"Approval threshold: ${s.approval_threshold_usd:.2f}", s.approval_threshold_usd > 0)
        self._add(f"Approval timeout: {s.approval_timeout_seconds}s", s.approval_timeout_seconds >= 60)
        self._add(
            f"Max position size: {s.max_position_size_pct}%",
            s.max_position_size_pct <= 5.0,
            f"{s.max_position_size_pct}% (recommend <= 5% to start)",
            warn_only=s.max_position_size_pct > 5.0,
        )
        self._add(f"Max daily loss: {s.max_daily_loss_pct}%", s.max_daily_loss_pct <= 5.0)

    async def run(self) -> bool:
        await self.check_vault()
        self.check_jwt()
        await self.check_database()
        await self.check_redis()
        await self.check_exchange()
        self.check_qdrant()
        await self.check_notifications()
        await self.check_paper_history()
        self.check_settings()
        return not any(item.status == "FAIL" and item.critical for item in self.results)


async def _main():
    checker = PreflightChecker()
    safe = await checker.run()
    for result in checker.results:
        print(f"[{result.status}] {result.name} {result.detail}".rstrip())
    sys.exit(0 if safe else 1)


if __name__ == "__main__":
    asyncio.run(_main())
