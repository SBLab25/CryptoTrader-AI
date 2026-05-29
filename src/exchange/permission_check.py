"""Exchange permission verification before live startup."""

from __future__ import annotations

import inspect
import os
import sys
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

MINIMUM_BALANCE_USD = float(os.getenv("MIN_LIVE_BALANCE_USD", "50"))


@dataclass
class PermissionCheckResult:
    passed: bool
    api_key_valid: bool = False
    trade_enabled: bool = False
    withdraw_disabled: bool = False
    ip_whitelisted: bool = False
    balance_sufficient: bool = False
    balance_usd: float = 0.0
    error: Optional[str] = None

    def print_report(self) -> None:
        print(f"Exchange permission check: {'PASS' if self.passed else 'FAIL'}")


class ExchangePermissionChecker:
    def __init__(self, vault=None, exchange_id: str = "cryptocom", sandbox: bool = False) -> None:
        self._vault = vault
        self._exchange_id = exchange_id
        self._sandbox = sandbox

    async def verify_or_abort(self) -> None:
        result = await self.verify()
        result.print_report()
        if not result.passed:
            log.error("live_permission_check_failed", error=result.error)
            sys.exit(1)

    async def verify(self) -> PermissionCheckResult:
        try:
            api_key, api_secret = await self._get_keys()
        except Exception as exc:
            return PermissionCheckResult(passed=False, error=str(exc))
        try:
            import ccxt.async_support as ccxt
        except ImportError:
            return PermissionCheckResult(passed=False, error="ccxt not installed")

        exchange = None
        try:
            exchange_class = getattr(ccxt, self._exchange_id)
            exchange = exchange_class({"apiKey": api_key, "secret": api_secret, "sandbox": self._sandbox})
            result = PermissionCheckResult(passed=False)
            balance = await exchange.fetch_balance()
            result.api_key_valid = True
            usdt_balance = (balance.get("USDT", {}) or {}).get("free", 0) or (balance.get("USD", {}) or {}).get("free", 0)
            result.balance_usd = float(usdt_balance or 0.0)
            result.balance_sufficient = result.balance_usd >= MINIMUM_BALANCE_USD
            perms = await self._fetch_permissions(exchange)
            result.trade_enabled = perms.get("trade_enabled", False)
            result.withdraw_disabled = not perms.get("withdraw_enabled", True)
            result.ip_whitelisted = perms.get("ip_restricted", False)
            result.passed = result.api_key_valid and result.trade_enabled and result.withdraw_disabled and result.balance_sufficient
            return result
        except Exception as exc:
            return PermissionCheckResult(passed=False, error=f"Unexpected error: {str(exc)[:100]}")
        finally:
            if exchange is not None:
                try:
                    await exchange.close()
                except Exception:
                    pass

    async def _get_keys(self) -> tuple[str, str]:
        if self._vault is not None:
            getter = getattr(self._vault, "get", None)
            if getter is not None:
                try:
                    api_key = getter("crypto/exchange", "api_key")
                    api_secret = getter("crypto/exchange", "api_secret")
                    if inspect.isawaitable(api_key):
                        api_key = await api_key
                    if inspect.isawaitable(api_secret):
                        api_secret = await api_secret
                    if api_key and api_secret:
                        return api_key, api_secret
                except TypeError:
                    pass
                except Exception:
                    pass
        api_key = os.getenv("CRYPTOCOM_API_KEY", "")
        api_secret = os.getenv("CRYPTOCOM_API_SECRET", "")
        if not api_key or not api_secret:
            raise ValueError("No API keys found in Vault or environment")
        return api_key, api_secret

    async def _fetch_permissions(self, exchange) -> dict:
        perms = {"trade_enabled": True, "withdraw_enabled": False, "ip_restricted": False}
        try:
            if self._exchange_id == "cryptocom" and hasattr(exchange, "privateGetPrivateGetAccountSummary"):
                info = await exchange.privateGetPrivateGetAccountSummary()
                accounts = info.get("result", {}).get("data", [{}])
                if accounts:
                    account = accounts[0]
                    perms["trade_enabled"] = account.get("trade_enabled", True)
                    perms["withdraw_enabled"] = account.get("withdrawal_enabled", False)
        except Exception:
            pass
        return perms
