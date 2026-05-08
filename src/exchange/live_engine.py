"""Live execution engine using Vault-managed keys and circuit breaker protection."""

from __future__ import annotations

from typing import Optional

from src.core.config import settings
from src.core.vault import get_vault_client
from src.utils.circuit_breaker import CircuitBreaker
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LiveEngine:
    def __init__(self, vault=None):
        self._vault = vault
        self._exchange = None
        self._initialised = False

    async def initialise(self) -> None:
        if self._initialised:
            return
        if settings.cryptocom_sandbox:
            raise RuntimeError(
                "CRYPTOCOM_SANDBOX=True is set but LiveEngine was requested. "
                "Disable sandbox before using live trading."
            )

        try:
            import ccxt.async_support as ccxt
        except ImportError as exc:
            raise ImportError("ccxt is required for live trading support") from exc

        if self._vault is None:
            self._vault = get_vault_client(settings.vault_addr, settings.vault_token)
        if self._vault is None:
            raise RuntimeError("Vault is required for live trading keys")

        api_key = self._vault.get("exchange_api_key")
        api_secret = self._vault.get("exchange_api_secret")
        self._exchange = ccxt.cryptocom(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        await self._verify_permissions()
        self._initialised = True
        del api_key, api_secret

    async def _verify_permissions(self) -> None:
        try:
            accounts = await self._exchange.fetch_accounts()
            if accounts and "withdraw" in str(accounts).lower():
                raise RuntimeError(
                    "CRITICAL: Exchange API key has 'withdraw' permission. "
                    "Use a trade-only key for automated trading."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(f"[LIVE] Could not verify permissions: {exc}")

    async def place_order(
        self,
        symbol: str,
        side: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        size_pct: float = 0.02,
    ) -> Optional[dict]:
        if not self._initialised:
            await self.initialise()

        ccxt_symbol = symbol.replace("_", "/")
        async with CircuitBreaker("cryptocom"):
            ticker = await self._exchange.fetch_ticker(ccxt_symbol)
            current_price = float(ticker["last"])
            balance = await self._exchange.fetch_balance()
            usdt_free = float(balance.get("USDT", {}).get("free", 0))
            amount_usdt = usdt_free * size_pct
            if amount_usdt < 10:
                logger.warning(f"[LIVE] Insufficient USDT balance for {symbol}: {usdt_free}")
                return None

            amount_asset = amount_usdt / current_price
            order = await self._exchange.create_order(
                symbol=ccxt_symbol,
                type="market",
                side=side.lower(),
                amount=round(amount_asset, 8),
                params={},
            )
            await self._audit_order(order, symbol, side, stop_loss, take_profit)
            await self._notify_order(order, symbol, side, current_price, stop_loss, take_profit, amount_usdt)
            return order

    async def _audit_order(
        self,
        order: dict,
        symbol: str,
        side: str,
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> None:
        try:
            from src.api.middleware.audit_logger import audit_log

            await audit_log(
                event_type="TRADE_OPENED",
                entity_id=str(order.get("id", "")),
                entity_type="Order",
                actor="live_engine",
                details={
                    "symbol": symbol,
                    "side": side,
                    "order_id": order.get("id"),
                    "amount": order.get("amount"),
                    "price": order.get("price") or order.get("average"),
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "exchange": "cryptocom",
                },
            )
        except Exception as exc:
            logger.warning(f"[LIVE] Audit write failed: {exc}")

    async def _notify_order(
        self,
        order: dict,
        symbol: str,
        side: str,
        current_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        position_usd: float,
    ) -> None:
        try:
            from src.notifications.ntfy import notify_trade_opened

            await notify_trade_opened(
                symbol=symbol,
                side=side,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=1.0,
                position_usd=position_usd,
                strategy="live_engine",
            )
        except Exception as exc:
            logger.warning(f"[LIVE] Notification failed: {exc}")

    def __del__(self):
        if self._exchange is not None:
            try:
                self._exchange.apiKey = None
                self._exchange.secret = None
            except Exception:
                pass
