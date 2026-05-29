"""Absolute financial hard caps for live and paper trading."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class CapCheckResult:
    approved: bool
    reason: str
    cap_hit: Optional[str] = None


class HardCaps:
    def __init__(self) -> None:
        self._max_single: Optional[float] = None
        self._max_daily: Optional[float] = None
        self._loaded = False

    async def load_from_vault(self, vault_client) -> None:
        mode = os.getenv("TRADING_MODE", "paper").lower()
        max_single = await self._vault_get(vault_client, "max_single_trade_usd")
        max_daily = await self._vault_get(vault_client, "max_daily_loss_usd")
        if not max_single:
            max_single = os.getenv("MAX_SINGLE_TRADE_USD", "")
        if not max_daily:
            max_daily = os.getenv("MAX_DAILY_LOSS_USD", "")
        if mode == "live" and (not max_single or not max_daily):
            raise RuntimeError("Hard caps not configured for live mode")
        self._max_single = float(max_single) if max_single else None
        self._max_daily = float(max_daily) if max_daily else None
        self._loaded = True

    def load_from_env(self) -> None:
        self._max_single = float(os.getenv("MAX_SINGLE_TRADE_USD", "500"))
        self._max_daily = float(os.getenv("MAX_DAILY_LOSS_USD", "1000"))
        self._loaded = True

    async def _vault_get(self, vault_client, field: str) -> str:
        if vault_client is None:
            return ""
        getter = getattr(vault_client, "get", None)
        if getter is None:
            return ""
        try:
            value = getter("crypto/risk", field)
        except TypeError:
            try:
                value = getter(field)
            except Exception:
                return ""
        except Exception:
            return ""
        if inspect.isawaitable(value):
            value = await value
        return value or ""

    def check(self, usd_amount: float, daily_loss_usd: float = 0.0) -> CapCheckResult:
        if not self._loaded:
            self.load_from_env()
        if self._max_single is not None and usd_amount > self._max_single:
            return CapCheckResult(
                approved=False,
                reason=f"Trade ${usd_amount:.2f} exceeds MAX_SINGLE_TRADE_USD ${self._max_single:.2f}",
                cap_hit="single_trade",
            )
        if self._max_daily is not None and daily_loss_usd >= self._max_daily:
            return CapCheckResult(
                approved=False,
                reason=f"Daily loss ${daily_loss_usd:.2f} has reached MAX_DAILY_LOSS_USD ${self._max_daily:.2f}",
                cap_hit="daily_loss",
            )
        return CapCheckResult(approved=True, reason="within caps")

    @property
    def max_single_trade_usd(self) -> Optional[float]:
        return self._max_single

    @property
    def max_daily_loss_usd(self) -> Optional[float]:
        return self._max_daily

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def status(self) -> dict:
        return {
            "loaded": self._loaded,
            "max_single_trade_usd": self._max_single,
            "max_daily_loss_usd": self._max_daily,
        }


hard_caps = HardCaps()
