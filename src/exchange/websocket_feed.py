"""Phase 2 exchange websocket feed with Redis stream publication."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional

from src.core.config import settings
from src.core.models import OHLCV
from src.db.database import get_db_session
from src.db.redis_client import cb_is_open, cb_record_failure, cb_record_success, publish_tick
from src.db.timescale import OHLCVStore
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketFeed:
    RECONNECT_DELAY_SECONDS = 5
    MAX_RECONNECT_DELAY = 60

    def __init__(
        self,
        exchange_id: str = "cryptocom",
        symbols: Optional[list[str]] = None,
        timeframe: Optional[str] = None,
        on_tick: Optional[Callable] = None,
    ):
        self._exchange_id = exchange_id
        self._symbols = symbols or [s.replace("_", "/") for s in settings.symbol_list]
        self._timeframe = timeframe or settings.websocket_timeframe
        self._on_tick = on_tick
        self._running = False
        self._exchange = None
        self._reconnect_delay = self.RECONNECT_DELAY_SECONDS

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._connect_and_stream()
                self._reconnect_delay = self.RECONNECT_DELAY_SECONDS
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await cb_record_failure(self._exchange_id)
                logger.warning(f"[WS_FEED] connection error: {exc}")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self.MAX_RECONNECT_DELAY)
            finally:
                if self._exchange is not None:
                    try:
                        await self._exchange.close()
                    except Exception:
                        pass
                    self._exchange = None

    async def _connect_and_stream(self) -> None:
        if await cb_is_open(self._exchange_id):
            await asyncio.sleep(30)
            return

        try:
            import ccxt.pro as ccxt_pro  # type: ignore
        except ImportError as exc:
            raise RuntimeError("ccxt.pro is required for websocket mode") from exc

        exchange_class = getattr(ccxt_pro, self._exchange_id)
        self._exchange = exchange_class({"enableRateLimit": True})
        if settings.cryptocom_sandbox and hasattr(self._exchange, "set_sandbox_mode"):
            self._exchange.set_sandbox_mode(True)

        await self._exchange.load_markets()
        await cb_record_success(self._exchange_id)
        await asyncio.gather(*[self._stream_symbol(symbol) for symbol in self._symbols])

    async def _stream_symbol(self, symbol: str) -> None:
        while self._running:
            try:
                candles = await self._exchange.watch_ohlcv(symbol, self._timeframe)
                if not candles:
                    continue
                tick = self._normalize(symbol, candles[-1])
                await publish_tick(tick)
                asyncio.create_task(self._persist_tick(tick))
                if self._on_tick is not None:
                    await self._on_tick(tick)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(f"[WS_FEED] symbol error for {symbol}: {exc}")
                await asyncio.sleep(1)

    @staticmethod
    def _normalize(symbol: str, candle: list) -> dict:
        ts_ms, open_, high, low, close, volume = candle[:6]
        return {
            "symbol": symbol.replace("/", "_"),
            "timestamp": int(ts_ms),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
            "source": "websocket",
        }

    @staticmethod
    async def _persist_tick(tick: dict) -> None:
        try:
            ohlcv = OHLCV(
                timestamp=datetime.fromtimestamp(tick["timestamp"] / 1000, tz=timezone.utc),
                symbol=tick["symbol"],
                open=tick["open"],
                high=tick["high"],
                low=tick["low"],
                close=tick["close"],
                volume=tick["volume"],
                source=tick.get("source", "websocket"),
            )
            async with get_db_session() as session:
                await OHLCVStore.insert_tick(session, ohlcv)
        except Exception as exc:
            logger.warning(f"[WS_FEED] persist error for {tick['symbol']}: {exc}")

    async def stop(self) -> None:
        self._running = False
        if self._exchange is not None:
            await self._exchange.close()
