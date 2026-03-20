# File: src/exchange/ccxt_adapter.py
"""
Multi-Exchange Adapter via CCXT
Supports Binance, Coinbase, Bybit, OKX, KuCoin, and 100+ others.
Install ccxt: pip install ccxt

This adapter normalises OHLCV and order placement across all exchanges
behind a unified interface, so the rest of the system doesn't need to
change when you add a new exchange.
"""
from __future__ import annotations

from typing import List, Dict, Optional, Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CCXTAdapter:
    """
    Unified exchange interface using the CCXT library.
    Falls back gracefully if CCXT is not installed.

    Usage:
        adapter = CCXTAdapter("binance", api_key="...", api_secret="...", sandbox=True)
        await adapter.connect()
        ohlcv = await adapter.fetch_ohlcv("BTC/USDT", "15m", limit=100)
        ticker = await adapter.fetch_ticker("BTC/USDT")
        order = await adapter.place_market_order("BTC/USDT", "buy", 0.001)
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
        extra_params: Optional[Dict] = None,
    ):
        self.exchange_id = exchange_id.lower()
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.extra_params = extra_params or {}
        self._exchange = None
        self._available = False

    async def connect(self) -> bool:
        """Initialise the CCXT exchange instance"""
        try:
            import ccxt.async_support as ccxt  # type: ignore

            exchange_class = getattr(ccxt, self.exchange_id, None)
            if not exchange_class:
                logger.error(f"[CCXT] Exchange '{self.exchange_id}' not found in CCXT")
                return False

            self._exchange = exchange_class({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                **self.extra_params,
            })

            if self.sandbox and hasattr(self._exchange, "set_sandbox_mode"):
                self._exchange.set_sandbox_mode(True)
                logger.info(f"[CCXT] {self.exchange_id} sandbox mode enabled")

            await self._exchange.load_markets()
            self._available = True
            logger.info(f"[CCXT] Connected to {self.exchange_id} ✓")
            return True

        except ImportError:
            logger.warning(
                "[CCXT] ccxt not installed. Run: pip install ccxt\n"
                "       Multi-exchange support requires ccxt. "
                "Using Crypto.com MCP for now."
            )
            return False
        except Exception as e:
            logger.error(f"[CCXT] Failed to connect to {self.exchange_id}: {e}")
            return False

    async def close(self) -> None:
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception:
                pass

    def _require_ccxt(self) -> bool:
        if not self._available or not self._exchange:
            logger.warning("[CCXT] Exchange not connected")
            return False
        return True

    # ── Market Data ───────────────────────────────────────────────────────────

    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Fetch latest ticker.
        Returns normalised dict: {price, bid, ask, volume, change_pct, high, low}
        """
        if not self._require_ccxt():
            return None
        try:
            raw = await self._exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "price": raw.get("last") or raw.get("close", 0),
                "bid": raw.get("bid", 0),
                "ask": raw.get("ask", 0),
                "volume_24h": raw.get("quoteVolume") or raw.get("baseVolume", 0),
                "change_24h_pct": raw.get("percentage", 0),
                "high_24h": raw.get("high", 0),
                "low_24h": raw.get("low", 0),
                "exchange": self.exchange_id,
            }
        except Exception as e:
            logger.error(f"[CCXT] fetch_ticker {symbol}: {e}")
            return None

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch OHLCV candles.
        Returns list of {timestamp, open, high, low, close, volume}
        """
        if not self._require_ccxt():
            return []
        try:
            raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return [
                {
                    "timestamp": row[0],
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in raw
            ]
        except Exception as e:
            logger.error(f"[CCXT] fetch_ohlcv {symbol}: {e}")
            return []

    async def fetch_orderbook(self, symbol: str, depth: int = 10) -> Optional[Dict]:
        if not self._require_ccxt():
            return None
        try:
            book = await self._exchange.fetch_order_book(symbol, depth)
            return {
                "bids": book.get("bids", [])[:depth],
                "asks": book.get("asks", [])[:depth],
            }
        except Exception as e:
            logger.error(f"[CCXT] fetch_orderbook {symbol}: {e}")
            return None

    # ── Order Execution ───────────────────────────────────────────────────────

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Place a market order.
        Returns normalised order dict or None on failure.
        """
        if not self._require_ccxt():
            return None
        try:
            order = await self._exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=params or {},
            )
            logger.info(f"[CCXT] Market order placed: {side} {amount} {symbol} → {order.get('id')}")
            return self._normalise_order(order)
        except Exception as e:
            logger.error(f"[CCXT] place_market_order {symbol}: {e}")
            return None

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        if not self._require_ccxt():
            return None
        try:
            order = await self._exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=price,
                params=params or {},
            )
            logger.info(f"[CCXT] Limit order placed: {side} {amount} {symbol} @ {price}")
            return self._normalise_order(order)
        except Exception as e:
            logger.error(f"[CCXT] place_limit_order {symbol}: {e}")
            return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if not self._require_ccxt():
            return False
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"[CCXT] cancel_order {order_id}: {e}")
            return False

    async def fetch_balance(self) -> Dict[str, float]:
        """Returns {asset: free_balance} dict"""
        if not self._require_ccxt():
            return {}
        try:
            balance = await self._exchange.fetch_balance()
            return {
                asset: info["free"]
                for asset, info in balance.items()
                if isinstance(info, dict) and info.get("free", 0) > 0
            }
        except Exception as e:
            logger.error(f"[CCXT] fetch_balance: {e}")
            return {}

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        if not self._require_ccxt():
            return []
        try:
            orders = await self._exchange.fetch_open_orders(symbol)
            return [self._normalise_order(o) for o in orders]
        except Exception as e:
            logger.error(f"[CCXT] fetch_open_orders: {e}")
            return []

    def _normalise_order(self, order: Dict) -> Dict:
        return {
            "order_id": order.get("id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "type": order.get("type"),
            "amount": order.get("amount"),
            "price": order.get("price"),
            "status": order.get("status"),
            "filled": order.get("filled", 0),
            "remaining": order.get("remaining"),
            "cost": order.get("cost"),
            "exchange": self.exchange_id,
        }

    @property
    def is_connected(self) -> bool:
        return self._available

    # ── Supported Exchanges ───────────────────────────────────────────────────

    @staticmethod
    def supported_exchanges() -> List[str]:
        try:
            import ccxt  # type: ignore
            return ccxt.exchanges
        except ImportError:
            return [
                "binance", "coinbase", "bybit", "okx", "kucoin",
                "kraken", "bitfinex", "huobi", "gate", "mexc",
            ]


# ── Multi-Exchange Manager ────────────────────────────────────────────────────

class MultiExchangeManager:
    """
    Manages connections to multiple exchanges simultaneously.
    Aggregates market data for best price discovery across exchanges.
    """

    def __init__(self):
        self._adapters: Dict[str, CCXTAdapter] = {}

    def add_exchange(
        self,
        exchange_id: str,
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
    ) -> None:
        self._adapters[exchange_id] = CCXTAdapter(
            exchange_id, api_key, api_secret, sandbox
        )

    async def connect_all(self) -> Dict[str, bool]:
        results = {}
        for exchange_id, adapter in self._adapters.items():
            results[exchange_id] = await adapter.connect()
        return results

    async def close_all(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()

    async def get_best_price(self, symbol: str) -> Optional[Dict]:
        """
        Fetch ticker from all exchanges and return the one with the best
        ask price (for buys) across all connected exchanges.
        """
        best = None
        for exchange_id, adapter in self._adapters.items():
            if not adapter.is_connected:
                continue
            ticker = await adapter.fetch_ticker(symbol)
            if ticker and ticker.get("price"):
                if best is None or ticker["ask"] < best["ask"]:
                    best = ticker
        return best

    async def aggregate_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        prefer_exchange: Optional[str] = None,
    ) -> List[Dict]:
        """Get OHLCV from preferred exchange or first available"""
        if prefer_exchange and prefer_exchange in self._adapters:
            data = await self._adapters[prefer_exchange].fetch_ohlcv(symbol, timeframe, limit)
            if data:
                return data

        for adapter in self._adapters.values():
            if adapter.is_connected:
                data = await adapter.fetch_ohlcv(symbol, timeframe, limit)
                if data:
                    return data
        return []

    @property
    def connected_exchanges(self) -> List[str]:
        return [eid for eid, a in self._adapters.items() if a.is_connected]
