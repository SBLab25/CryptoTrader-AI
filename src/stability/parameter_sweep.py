"""Fast parameter sweep for paper-trading calibration."""

from __future__ import annotations

import asyncio
import itertools
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PARAM_GRID = {
    "rsi_period": [10, 14, 20],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "ema_fast": [10, 20],
    "ema_slow": [50, 100],
    "confidence_floor": [0.55, 0.60, 0.65],
    "position_size_pct": [0.02, 0.03, 0.05],
    "atr_sl_multiplier": [1.5, 2.0, 2.5],
    "atr_tp_multiplier": [2.5, 3.0, 4.0],
}

FAST_GRID = {
    "rsi_period": [14],
    "rsi_oversold": [30, 35],
    "rsi_overbought": [65, 70],
    "ema_fast": [20],
    "ema_slow": [50],
    "confidence_floor": [0.55, 0.60],
    "position_size_pct": [0.03],
    "atr_sl_multiplier": [1.5, 2.0],
    "atr_tp_multiplier": [3.0],
}


@dataclass
class StrategyParams:
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    ema_fast: int = 20
    ema_slow: int = 50
    confidence_floor: float = 0.55
    position_size_pct: float = 0.03
    atr_sl_multiplier: float = 1.5
    atr_tp_multiplier: float = 3.0

    def to_dict(self) -> dict:
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "confidence_floor": self.confidence_floor,
            "position_size_pct": self.position_size_pct,
            "atr_sl_multiplier": self.atr_sl_multiplier,
            "atr_tp_multiplier": self.atr_tp_multiplier,
        }


@dataclass
class SweepResult:
    params: StrategyParams
    sharpe: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    total_pnl: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _ema(prices: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    result = [0.0 for _ in prices]
    result[0] = prices[0]
    for i in range(1, len(prices)):
        result[i] = prices[i] * k + result[i - 1] * (1 - k)
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float]:
    delta = [0.0]
    for i in range(1, len(closes)):
        delta.append(closes[i] - closes[i - 1])
    gains = [value if value > 0 else 0.0 for value in delta]
    losses = [-value if value < 0 else 0.0 for value in delta]
    avg_gain = [0.0 for _ in closes]
    avg_loss = [0.0 for _ in closes]
    if len(closes) > period:
        avg_gain[period] = _mean(gains[1 : period + 1])
        avg_loss[period] = _mean(losses[1 : period + 1])
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period
    result: list[float] = []
    for gain, loss in zip(avg_gain, avg_loss):
        rs = 100.0 if loss == 0 else gain / loss
        value = 100.0 - (100.0 / (1.0 + rs))
        result.append(max(0.0, min(100.0, value)))
    return result


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    prev_close = [closes[0], *closes[:-1]]
    tr = [
        max(high - low, abs(high - prev), abs(low - prev))
        for high, low, prev in zip(highs, lows, prev_close)
    ]
    atr = [0.0 for _ in tr]
    if len(tr) > period:
        atr[period] = _mean(tr[: period + 1])
    for i in range(period + 1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _backtest(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    params: StrategyParams,
    starting_capital: float = 1000.0,
) -> SweepResult:
    n = len(closes)
    if n < params.ema_slow + 20:
        return SweepResult(params, -99.0, 0.0, 0.0, 1.0, 0, 0.0)

    rsi = _rsi(closes, params.rsi_period)
    ema_fast = _ema(closes, params.ema_fast)
    ema_slow = _ema(closes, params.ema_slow)
    atr = _atr(highs, lows, closes, 14)

    capital = starting_capital
    equity = [capital]
    trades_pnl: list[float] = []
    in_trade = False
    entry_price = stop_loss = take_profit = 0.0
    direction = 0
    warmup = max(params.ema_slow, params.rsi_period) + 5

    for i in range(warmup, n):
        price = closes[i]
        if in_trade:
            hit_sl = (direction == 1 and price <= stop_loss) or (direction == -1 and price >= stop_loss)
            hit_tp = (direction == 1 and price >= take_profit) or (direction == -1 and price <= take_profit)
            if hit_sl or hit_tp:
                pnl_pct = direction * (price - entry_price) / entry_price
                trade_pnl = capital * params.position_size_pct * pnl_pct
                capital += trade_pnl
                trades_pnl.append(trade_pnl)
                equity.append(capital)
                in_trade = False

        if not in_trade:
            bullish = rsi[i] < params.rsi_oversold and ema_fast[i] > ema_slow[i] and atr[i] > 0
            bearish = rsi[i] > params.rsi_overbought and ema_fast[i] < ema_slow[i] and atr[i] > 0
            if bullish:
                direction = 1
                entry_price = price
                stop_loss = price - params.atr_sl_multiplier * atr[i]
                take_profit = price + params.atr_tp_multiplier * atr[i]
                in_trade = True
            elif bearish:
                direction = -1
                entry_price = price
                stop_loss = price + params.atr_sl_multiplier * atr[i]
                take_profit = price - params.atr_tp_multiplier * atr[i]
                in_trade = True

    if len(equity) < 2:
        return SweepResult(params, -99.0, 0.0, 0.0, 1.0, 0, 0.0)
    returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity))]
    sharpe = float((_mean(returns) / (_std(returns) + 1e-9)) * math.sqrt(252 * 24))
    wins = [p for p in trades_pnl if p > 0]
    losses = [abs(p) for p in trades_pnl if p < 0]
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        max_dd = max(max_dd, dd)
    return SweepResult(
        params=params,
        sharpe=sharpe,
        win_rate=float(len(wins) / max(len(trades_pnl), 1)),
        profit_factor=float(sum(wins) / max(sum(losses), 1e-9)),
        max_drawdown=float(max_dd),
        total_trades=len(trades_pnl),
        total_pnl=float(capital - starting_capital),
    )


class ParameterSweep:
    def __init__(self, ts_store=None) -> None:
        self._ts_store = ts_store

    async def _load_data(self, symbol: str, timeframe: str, lookback_days: int) -> tuple[list[float], list[float], list[float]]:
        if self._ts_store is None:
            n = max(lookback_days * 24, 120)
            closes = [65000 + 5000 * math.sin((4 * math.pi * i) / max(n - 1, 1)) + random.gauss(0, 200) for i in range(n)]
            highs = [close + abs(random.gauss(0, 150)) for close in closes]
            lows = [close - abs(random.gauss(0, 150)) for close in closes]
            return closes, highs, lows

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        candles = await self._ts_store.query_range(symbol, timeframe, start, end, limit=lookback_days * 25)
        closes = [float(c.close) for c in candles]
        highs = [float(c.high) for c in candles]
        lows = [float(c.low) for c in candles]
        return closes, highs, lows

    async def run(
        self,
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        lookback_days: int = 30,
        fast: bool = True,
    ) -> list[SweepResult]:
        closes, highs, lows = await self._load_data(symbol, timeframe, lookback_days)
        grid = FAST_GRID if fast else PARAM_GRID
        keys = list(grid.keys())
        results: list[SweepResult] = []
        for combo in itertools.product(*[grid[k] for k in keys]):
            params = StrategyParams(**dict(zip(keys, combo)))
            result = _backtest(closes, highs, lows, params)
            if result.total_trades >= 5:
                results.append(result)
        results.sort(key=lambda item: item.sharpe, reverse=True)
        return results

    @staticmethod
    def print_top(results: list[SweepResult], n: int = 10) -> None:
        if not results:
            print("No results.")
            return
        for idx, result in enumerate(results[:n], 1):
            print(
                f"#{idx} sharpe={result.sharpe:.3f} win={result.win_rate:.1%} "
                f"pf={result.profit_factor:.2f} dd={result.max_drawdown:.1%} "
                f"trades={result.total_trades} pnl={result.total_pnl:.2f}"
            )

    @staticmethod
    async def write_best_to_vault(best: SweepResult, vault_client, path: str = "crypto/strategy") -> bool:
        if vault_client is None:
            return False
        writer = getattr(vault_client, "put", None)
        if writer is None:
            writer = getattr(vault_client, "write", None)
        if writer is None:
            return False
        result = writer(path, best.params.to_dict())
        if hasattr(result, "__await__"):
            await result
        return True


async def _main() -> None:
    sweep = ParameterSweep()
    results = await sweep.run()
    sweep.print_top(results)


if __name__ == "__main__":
    asyncio.run(_main())
