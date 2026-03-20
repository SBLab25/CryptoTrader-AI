# File: src/agents/market_analyst.py
"""
Market Analyst Agent
Collects real-time market data from Crypto.com Exchange (via MCP) and prepares
OHLCV data for signal generation.
"""
import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime

from src.core.models import MarketData
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Crypto.com MCP endpoint (available in user's connected tools)
CRYPTOCOM_MCP_URL = "https://mcp.crypto.com/market-data/mcp"


class MarketAnalystAgent:
    """
    Fetches and normalizes market data from Crypto.com exchange.
    In production, also supports CCXT for multi-exchange aggregation.
    """

    def __init__(self):
        self._price_cache: Dict[str, MarketData] = {}
        self._ohlcv_cache: Dict[str, List[dict]] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )

    async def stop(self):
        if self.session:
            await self.session.close()

    async def fetch_ticker(self, symbol: str) -> Optional[MarketData]:
        """
        Fetch current ticker for a symbol from Crypto.com public API.
        Symbol format: BTC_USDT
        """
        url = "https://api.crypto.com/exchange/v1/public/get-ticker"
        try:
            async with self.session.get(url, params={"instrument_name": symbol}) as resp:
                data = await resp.json()
                
            ticker = data.get("result", {}).get("data", {})
            if not ticker:
                logger.warning(f"No ticker data for {symbol}")
                return None

            market_data = MarketData(
                symbol=symbol,
                price=float(ticker.get("a", ticker.get("k", 0))),  # last trade price
                bid=float(ticker.get("b", 0)),
                ask=float(ticker.get("k", 0)),
                volume_24h=float(ticker.get("vv", 0)),
                change_24h_pct=float(ticker.get("c", 0)),
                high_24h=float(ticker.get("h", 0)),
                low_24h=float(ticker.get("l", 0)),
            )
            self._price_cache[symbol] = market_data
            return market_data

        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            # Return cached data if available
            return self._price_cache.get(symbol)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 100,
    ) -> List[dict]:
        """
        Fetch OHLCV candlestick data.
        Returns list of {timestamp, open, high, low, close, volume}
        """
        url = "https://api.crypto.com/exchange/v1/public/get-candlestick"
        try:
            async with self.session.get(
                url,
                params={"instrument_name": symbol, "timeframe": timeframe, "count": limit}
            ) as resp:
                data = await resp.json()

            candles = data.get("result", {}).get("data", [])
            ohlcv = [
                {
                    "timestamp": int(c.get("t", 0)),
                    "open": float(c.get("o", 0)),
                    "high": float(c.get("h", 0)),
                    "low": float(c.get("l", 0)),
                    "close": float(c.get("c", 0)),
                    "volume": float(c.get("v", 0)),
                }
                for c in candles
            ]

            # Sort ascending by timestamp
            ohlcv.sort(key=lambda x: x["timestamp"])
            self._ohlcv_cache[symbol] = ohlcv
            return ohlcv

        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return self._ohlcv_cache.get(symbol, [])

    async def fetch_all_symbols(
        self,
        symbols: List[str],
    ) -> tuple[Dict[str, MarketData], Dict[str, List[dict]]]:
        """
        Fetch ticker + OHLCV for all symbols concurrently.
        Returns (market_data_map, ohlcv_map)
        """
        ticker_tasks = [self.fetch_ticker(s) for s in symbols]
        ohlcv_tasks = [self.fetch_ohlcv(s, timeframe="15m", limit=100) for s in symbols]

        ticker_results = await asyncio.gather(*ticker_tasks, return_exceptions=True)
        ohlcv_results = await asyncio.gather(*ohlcv_tasks, return_exceptions=True)

        market_data_map = {}
        ohlcv_map = {}

        for symbol, ticker, ohlcv in zip(symbols, ticker_results, ohlcv_results):
            if isinstance(ticker, MarketData):
                market_data_map[symbol] = ticker
            elif isinstance(ticker, Exception):
                logger.error(f"Ticker error for {symbol}: {ticker}")

            if isinstance(ohlcv, list):
                ohlcv_map[symbol] = ohlcv
            elif isinstance(ohlcv, Exception):
                logger.error(f"OHLCV error for {symbol}: {ohlcv}")

        logger.info(
            f"[MARKET] Fetched data for {len(market_data_map)}/{len(symbols)} symbols"
        )
        return market_data_map, ohlcv_map

    def get_current_prices(self) -> Dict[str, float]:
        """Get latest cached prices as symbol -> price dict"""
        return {
            symbol: md.price
            for symbol, md in self._price_cache.items()
        }

    def get_cached_market_data(self, symbol: str) -> Optional[MarketData]:
        return self._price_cache.get(symbol)
