# File: src/exchange/paper_engine.py
"""
Exchange Tools
Wraps Crypto.com Exchange API (and optionally CCXT for multi-exchange)
Supports paper trading mode for safe simulation
"""
import asyncio
import aiohttp
import hmac
import hashlib
import time
import json
from typing import List, Dict, Optional, Any
from datetime import datetime

from src.core.models import Trade, OrderSide, OrderStatus, MarketData
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PaperTradingEngine:
    """
    Simulates exchange order execution without real money.
    Tracks virtual positions and balance.
    """
    def __init__(self, initial_capital: float = 10000.0):
        self.balance = {"USDT": initial_capital}
        self.positions: Dict[str, dict] = {}
        self.orders: Dict[str, dict] = {}
        self.order_counter = 0

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        self.order_counter += 1
        order_id = f"PAPER-{self.order_counter:06d}"

        base_asset = symbol.split("_")[0]
        quote_asset = symbol.split("_")[1] if "_" in symbol else "USDT"
        cost = quantity * price

        if side == "buy":
            if self.balance.get(quote_asset, 0) < cost:
                return {"error": "Insufficient balance", "order_id": None}
            self.balance[quote_asset] = self.balance.get(quote_asset, 0) - cost
            self.balance[base_asset] = self.balance.get(base_asset, 0) + quantity
            self.positions[order_id] = {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "entry_price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "status": "open",
                "order_id": order_id,
            }
        else:
            if self.balance.get(base_asset, 0) < quantity:
                return {"error": "Insufficient asset balance", "order_id": None}
            self.balance[base_asset] -= quantity
            self.balance[quote_asset] = self.balance.get(quote_asset, 0) + cost

        logger.info(f"[PAPER] {side.upper()} {quantity} {symbol} @ {price} | OrderID: {order_id}")
        return {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "status": "filled",
            "is_paper": True,
        }

    def close_position(self, order_id: str, exit_price: float) -> dict:
        if order_id not in self.positions:
            return {"error": "Position not found"}
        
        pos = self.positions[order_id]
        quantity = pos["quantity"]
        entry_price = pos["entry_price"]
        symbol = pos["symbol"]
        base_asset = symbol.split("_")[0]
        quote_asset = symbol.split("_")[1] if "_" in symbol else "USDT"

        if pos["side"] == "buy":
            pnl = (exit_price - entry_price) * quantity
            self.balance[quote_asset] = self.balance.get(quote_asset, 0) + (quantity * exit_price)
            if base_asset in self.balance:
                self.balance[base_asset] -= quantity
        else:
            pnl = (entry_price - exit_price) * quantity
            self.balance[base_asset] = self.balance.get(base_asset, 0) + quantity

        pos["status"] = "closed"
        pos["exit_price"] = exit_price
        pos["pnl"] = round(pnl, 4)
        
        logger.info(f"[PAPER] Closed {order_id} @ {exit_price} | PnL: {pnl:+.4f} USDT")
        return pos

    def get_balance(self) -> Dict[str, float]:
        return self.balance.copy()

    def check_stop_take_profit(self, current_prices: Dict[str, float]) -> List[dict]:
        """Check if any positions hit stop-loss or take-profit"""
        triggered = []
        for order_id, pos in list(self.positions.items()):
            if pos["status"] != "open":
                continue
            symbol = pos["symbol"]
            price = current_prices.get(symbol)
            if not price:
                continue

            if pos["side"] == "buy":
                if price <= pos["stop_loss"]:
                    result = self.close_position(order_id, pos["stop_loss"])
                    result["trigger"] = "stop_loss"
                    triggered.append(result)
                elif price >= pos["take_profit"]:
                    result = self.close_position(order_id, pos["take_profit"])
                    result["trigger"] = "take_profit"
                    triggered.append(result)
        return triggered


class CryptocomExchangeClient:
    """
    Crypto.com Exchange REST API client
    Docs: https://exchange-docs.crypto.com
    """
    BASE_URL = "https://api.crypto.com/exchange/v1"
    SANDBOX_URL = "https://uat-api.3ona.co/exchange/v1"

    def __init__(self, api_key: str, api_secret: str, sandbox: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.SANDBOX_URL if sandbox else self.BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _sign(self, method: str, params: dict, nonce: int) -> str:
        param_string = ""
        if params:
            param_string = "".join(
                f"{k}{v}" for k, v in sorted(params.items())
            )
        payload = f"{method}{self.api_key}{param_string}{nonce}"
        return hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        signed: bool = False,
    ) -> dict:
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        body = {}

        if signed:
            nonce = int(time.time() * 1000)
            body = {
                "id": nonce,
                "method": endpoint,
                "api_key": self.api_key,
                "params": params or {},
                "nonce": nonce,
            }
            body["sig"] = self._sign(endpoint, params or {}, nonce)

        try:
            if method == "GET":
                async with self.session.get(url, params=params, headers=headers) as resp:
                    return await resp.json()
            else:
                async with self.session.post(url, json=body, headers=headers) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Exchange API error [{endpoint}]: {e}")
            return {"error": str(e)}

    async def get_ticker(self, instrument_name: str) -> dict:
        result = await self._request("GET", "public/get-ticker", {"instrument_name": instrument_name})
        return result.get("result", {}).get("data", {})

    async def get_orderbook(self, instrument_name: str, depth: int = 10) -> dict:
        result = await self._request(
            "GET", "public/get-book",
            {"instrument_name": instrument_name, "depth": depth}
        )
        return result.get("result", {}).get("data", {})

    async def get_candlestick(self, instrument_name: str, timeframe: str = "5m") -> list:
        result = await self._request(
            "GET", "public/get-candlestick",
            {"instrument_name": instrument_name, "timeframe": timeframe}
        )
        data = result.get("result", {}).get("data", [])
        return [
            {
                "timestamp": candle.get("t"),
                "open": float(candle.get("o", 0)),
                "high": float(candle.get("h", 0)),
                "low": float(candle.get("l", 0)),
                "close": float(candle.get("c", 0)),
                "volume": float(candle.get("v", 0)),
            }
            for candle in data
        ]

    async def place_order(
        self,
        instrument_name: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        client_oid: Optional[str] = None,
    ) -> dict:
        params = {
            "instrument_name": instrument_name,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
        }
        if price:
            params["price"] = str(price)
        if client_oid:
            params["client_oid"] = client_oid

        result = await self._request("POST", "private/create-order", params, signed=True)
        return result.get("result", {})

    async def cancel_order(self, instrument_name: str, order_id: str) -> dict:
        params = {"instrument_name": instrument_name, "order_id": order_id}
        result = await self._request("POST", "private/cancel-order", params, signed=True)
        return result.get("result", {})

    async def get_account_balance(self) -> dict:
        result = await self._request("POST", "private/user-balance", {}, signed=True)
        return result.get("result", {})

    async def get_open_orders(self, instrument_name: Optional[str] = None) -> list:
        params = {}
        if instrument_name:
            params["instrument_name"] = instrument_name
        result = await self._request("POST", "private/get-open-orders", params, signed=True)
        return result.get("result", {}).get("order_list", [])


class MockExchangeClient:
    """
    Mock exchange client using Crypto.com MCP data (read-only) for analysis
    Combined with paper trading engine for order simulation
    """
    def __init__(self, paper_engine: PaperTradingEngine):
        self.paper_engine = paper_engine
        self._price_cache: Dict[str, float] = {}

    def update_price(self, symbol: str, price: float):
        self._price_cache[symbol] = price

    def get_price(self, symbol: str) -> Optional[float]:
        return self._price_cache.get(symbol)

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        return self.paper_engine.place_order(
            symbol, side, quantity, price, stop_loss, take_profit
        )
