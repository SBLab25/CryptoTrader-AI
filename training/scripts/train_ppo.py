"""CLI entry point for Phase 5 PPO training."""

from __future__ import annotations

import argparse

from src.agents.rl.trainer import RLTrainer
from training.data.download_historical import HistoricalDataDownloader, precompute_indicators


async def _download_if_needed(symbol: str, timeframe: str, days: int):
    downloader = HistoricalDataDownloader()
    path = await downloader.download(symbol=symbol, timeframe=timeframe, days=days, force=False)
    precompute_indicators(path)
    return path


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="Train a PPO model on historical crypto data.")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="30m")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--algorithm", default="ppo", choices=["ppo", "sac", "a2c"])
    args = parser.parse_args()

    parquet_path = asyncio.run(_download_if_needed(args.symbol, args.timeframe, args.days))
    trainer = RLTrainer(algorithm=args.algorithm)
    result = trainer.train(parquet_path=parquet_path, total_timesteps=args.timesteps)
    print(result)


if __name__ == "__main__":
    main()
