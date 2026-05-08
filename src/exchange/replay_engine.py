"""Historical replay engine for Phase 5 demo/training workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.config import settings
from src.core.models import OHLCV
from src.db.database import get_db_session
from src.db.redis_client import publish_tick
from src.db.timescale import OHLCVStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_DATA_DIR = Path("training/data/historical")
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class ReplayEngine:
    def __init__(
        self,
        data_paths: dict[str, str | Path],
        speed_multiplier: float = 100.0,
        timeframe: str = "30m",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        persist_to_db: bool = True,
        loop: bool = False,
    ) -> None:
        self._data_paths = {symbol: Path(path) for symbol, path in data_paths.items()}
        self._speed = max(speed_multiplier, 0.001)
        self._timeframe = timeframe
        self._start_date = start_date
        self._end_date = end_date
        self._persist_to_db = persist_to_db
        self._loop = loop
        self._running = False
        self._candle_interval = TIMEFRAME_SECONDS.get(timeframe, 1800)
        self._replay_interval = self._candle_interval / self._speed

    async def run(self) -> None:
        self._running = True
        while self._running:
            merged = self._load_and_merge()
            if merged.empty:
                logger.warning("[REPLAY] No replay data available")
                self._running = False
                return

            for _, row in merged.iterrows():
                if not self._running:
                    break

                tick = {
                    "symbol": row["symbol"],
                    "timestamp": int(row["timestamp"].timestamp() * 1000),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "source": "replay",
                }

                await publish_tick(tick)
                if self._persist_to_db:
                    asyncio.create_task(self._persist_tick(tick))
                await asyncio.sleep(self._replay_interval)

            if not self._loop:
                break
        self._running = False

    async def stop(self) -> None:
        self._running = False

    def _load_and_merge(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for symbol, path in self._data_paths.items():
            if not path.exists():
                logger.warning(f"[REPLAY] Missing replay file for {symbol}: {path}")
                continue

            frame = pd.read_parquet(str(path))
            if not pd.api.types.is_datetime64_any_dtype(frame["timestamp"]):
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            elif frame["timestamp"].dt.tz is None:
                frame["timestamp"] = frame["timestamp"].dt.tz_localize("UTC")

            if self._start_date:
                frame = frame[frame["timestamp"] >= pd.Timestamp(self._start_date, tz="UTC")]
            if self._end_date:
                frame = frame[frame["timestamp"] <= pd.Timestamp(self._end_date, tz="UTC")]

            frame = frame.copy()
            frame["symbol"] = symbol
            frames.append(frame)

        if not frames:
            return pd.DataFrame()

        merged = pd.concat(frames, ignore_index=True)
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        return merged

    @staticmethod
    async def _persist_tick(tick: dict) -> None:
        try:
            ts = datetime.fromtimestamp(tick["timestamp"] / 1000, tz=timezone.utc)
            candle = OHLCV(
                timestamp=ts,
                symbol=tick["symbol"],
                open=tick["open"],
                high=tick["high"],
                low=tick["low"],
                close=tick["close"],
                volume=tick["volume"],
                source="replay",
            )
            async with get_db_session() as session:
                await OHLCVStore.insert_tick(session, candle)
        except Exception as exc:
            logger.debug(f"[REPLAY] Persistence skipped: {exc}")

    @classmethod
    def from_settings(
        cls,
        speed_multiplier: Optional[float] = None,
        timeframe: Optional[str] = None,
        days: Optional[int] = None,
        **kwargs,
    ) -> "ReplayEngine":
        selected_timeframe = timeframe or settings.replay_timeframe
        selected_days = days or settings.replay_days
        selected_speed = speed_multiplier or settings.replay_speed
        data_paths: dict[str, Path] = {}

        for symbol in settings.symbol_list:
            path = DEFAULT_DATA_DIR / f"{symbol}_{selected_timeframe}_{selected_days}d.parquet"
            if path.exists():
                data_paths[symbol] = path
            else:
                logger.warning(f"[REPLAY] Missing historical dataset for {symbol}: {path}")

        if not data_paths:
            raise FileNotFoundError(
                f"No replay datasets found in {DEFAULT_DATA_DIR} for symbols: {', '.join(settings.symbol_list)}"
            )

        return cls(
            data_paths=data_paths,
            speed_multiplier=selected_speed,
            timeframe=selected_timeframe,
            **kwargs,
        )
