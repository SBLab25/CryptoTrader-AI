"""Phase 7 dashboard support routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.auth import get_current_user
from src.agents.orchestrator import TradingOrchestrator
from src.db.database import get_db_session
from src.db.timescale import OHLCVStore

router = APIRouter(prefix="/api", tags=["Dashboard"], dependencies=[Depends(get_current_user)])


@dataclass
class TrainingRuntimeState:
    running: bool = False
    symbol: str = "BTC_USDT"
    timesteps: int = 0
    speed_multiplier: int = 1
    episode: int = 0
    total_episodes: int = 0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_reward: float = 0.0
    best_reward: float = 0.0
    current_date: str | None = None
    checkpoint_saved: bool = False
    model_path: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


training_state = TrainingRuntimeState()


class TrainingStartRequest(BaseModel):
    symbol: str
    timesteps: int = 500_000
    speed_multiplier: int = 100


class TrainingLoadRequest(BaseModel):
    path: str


def bind_orchestrator(orchestrator: TradingOrchestrator) -> None:
    router.state = {"orchestrator": orchestrator}


def _orchestrator() -> TradingOrchestrator:
    orchestrator = getattr(router, "state", {}).get("orchestrator")
    if orchestrator is None:
        raise RuntimeError("Dashboard router not bound to orchestrator")
    return orchestrator


@router.get("/ohlcv")
async def get_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 300):
    candles: list[dict] = []
    async with get_db_session() as session:
        candles = await OHLCVStore.get_latest(session, symbol=symbol.upper(), limit=limit)

    if len(candles) < min(limit, 30):
        candles = await _orchestrator().market_analyst.fetch_ohlcv(symbol.upper(), timeframe=timeframe, limit=limit)

    def _to_ts(value):
        if isinstance(value, datetime):
            return int(value.replace(tzinfo=timezone.utc).timestamp())
        return int(value) // 1000 if int(value) > 10_000_000_000 else int(value)

    return [
        {
            "time": _to_ts(candle["timestamp"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0.0) or 0.0),
        }
        for candle in candles[-limit:]
    ]


@router.get("/training/status")
async def get_training_status():
    return {
        "running": training_state.running,
        "symbol": training_state.symbol,
        "timesteps": training_state.timesteps,
        "episode": training_state.episode,
        "total_episodes": training_state.total_episodes,
        "sharpe_ratio": training_state.sharpe_ratio,
        "win_rate": training_state.win_rate,
        "avg_reward": training_state.avg_reward,
        "best_reward": training_state.best_reward,
        "current_date": training_state.current_date,
        "replay_speed": training_state.speed_multiplier,
        "checkpoint_saved": training_state.checkpoint_saved,
        "model_path": training_state.model_path,
        "updated_at": training_state.updated_at.isoformat(),
    }


@router.post("/training/start")
async def start_training(body: TrainingStartRequest):
    training_state.running = True
    training_state.symbol = body.symbol.upper()
    training_state.timesteps = body.timesteps
    training_state.speed_multiplier = body.speed_multiplier
    training_state.episode = 1
    training_state.total_episodes = max(body.timesteps // 10_000, 1)
    training_state.current_date = datetime.now(timezone.utc).date().isoformat()
    training_state.checkpoint_saved = False
    training_state.touch()
    return {"status": "started", "symbol": training_state.symbol}


@router.post("/training/stop")
async def stop_training():
    training_state.running = False
    training_state.touch()
    return {"status": "stopped"}


@router.get("/training/checkpoints")
async def list_training_checkpoints():
    roots = [Path("training/models"), Path("training/checkpoints")]
    checkpoints: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".zip", ".pt", ".pth", ".ckpt", ".onnx"}:
                continue
            stat = path.stat()
            checkpoints.append(
                {
                    "name": path.name,
                    "path": path.as_posix(),
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return checkpoints[:50]


@router.post("/training/load-model")
async def load_training_model(body: TrainingLoadRequest):
    training_state.model_path = body.path
    training_state.checkpoint_saved = True
    training_state.touch()
    return {"status": "loaded", "path": body.path}
