"""Gym-compatible crypto trading environment used for Phase 5 RL work."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - exercised through fallback path
    gym = None
    spaces = None


class CryptoTradingEnv(gym.Env if gym else object):
    WINDOW_SIZE = 20
    OBS_OHLCV_DIM = WINDOW_SIZE * 5
    OBS_IND_DIM = 5
    OBS_PORT_DIM = 3
    OBS_TOTAL_DIM = OBS_OHLCV_DIM + OBS_IND_DIM + OBS_PORT_DIM

    POSITION_SIZES = [0.01, 0.02, 0.03, 0.04, 0.05]
    TRANSACTION_COST = 0.001
    MAX_LOSS_PCT = 0.50

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float = 10_000.0,
        min_episode_len: int = 50,
        max_episode_len: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> None:
        if len(data) < self.WINDOW_SIZE + 2:
            raise ValueError("RL environment requires at least 22 rows of OHLCV data")

        self.data = data.reset_index(drop=True)
        self.initial_capital = initial_capital
        self.min_episode_len = min_episode_len
        self.max_episode_len = max_episode_len or len(data)
        self._rng = np.random.default_rng(seed)

        if spaces is not None:
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(self.OBS_TOTAL_DIM,),
                dtype=np.float32,
            )
            self.action_space = spaces.MultiDiscrete([3, len(self.POSITION_SIZES)])

        self.current_step = 0
        self.episode_start = 0
        self.cash = initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.portfolio_values: list[float] = []
        self.max_portfolio = initial_capital
        self.total_trades = 0
        self.winning_trades = 0

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        earliest_start = self.WINDOW_SIZE
        latest_start = max(earliest_start, len(self.data) - self.min_episode_len - 1)
        self.episode_start = (
            earliest_start
            if latest_start <= earliest_start
            else int(self._rng.integers(earliest_start, latest_start))
        )

        self.current_step = self.episode_start
        self.cash = self.initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.portfolio_values = [self.initial_capital]
        self.max_portfolio = self.initial_capital
        self.total_trades = 0
        self.winning_trades = 0
        return self._get_observation(), self._get_info()

    def step(self, action) -> tuple[np.ndarray, float, bool, bool, dict]:
        direction_idx = int(action[0])
        size_idx = int(action[1])
        direction = ["HOLD", "BUY", "SELL"][direction_idx]
        size_pct = self.POSITION_SIZES[size_idx]

        current_candle = self.data.iloc[self.current_step]
        price = float(current_candle["close"])
        prev_portfolio = self.portfolio_values[-1]
        trade_cost = 0.0

        if direction == "BUY" and self.position == 0.0 and self.cash > 0:
            amount_usd = self.cash * size_pct
            fee = amount_usd * self.TRANSACTION_COST
            self.position = (amount_usd - fee) / price
            self.cash -= amount_usd
            self.entry_price = price
            trade_cost = fee
            self.total_trades += 1
        elif direction == "SELL" and self.position > 0.0:
            gross_proceeds = self.position * price
            fee = gross_proceeds * self.TRANSACTION_COST
            if price > self.entry_price:
                self.winning_trades += 1
            self.cash += gross_proceeds - fee
            self.position = 0.0
            self.entry_price = 0.0
            trade_cost = fee
            self.total_trades += 1

        portfolio_value = self.cash + self.position * price
        self.portfolio_values.append(portfolio_value)
        self.max_portfolio = max(self.max_portfolio, portfolio_value)

        reward = self._compute_reward(portfolio_value, prev_portfolio, trade_cost)

        self.current_step += 1
        terminated = (
            self.current_step >= len(self.data) - 1
            or (self.current_step - self.episode_start) >= self.max_episode_len
        )
        truncated = portfolio_value < self.initial_capital * (1 - self.MAX_LOSS_PCT)

        return self._get_observation(), reward, terminated, truncated, self._get_info()

    def render(self) -> None:
        if not self.portfolio_values:
            return
        portfolio_value = self.portfolio_values[-1]
        pnl_pct = (portfolio_value / self.initial_capital - 1) * 100
        print(f"Step {self.current_step} | Portfolio ${portfolio_value:,.2f} ({pnl_pct:+.2f}%)")

    def _get_observation(self) -> np.ndarray:
        start_idx = self.current_step - self.WINDOW_SIZE
        end_idx = self.current_step
        window = self.data.iloc[start_idx:end_idx]

        last_close = float(window.iloc[-1]["close"])
        norm = last_close if last_close > 0 else 1.0

        ohlcv = window[["open", "high", "low", "close", "volume"]].values.astype(np.float32)
        ohlcv[:, :4] /= norm
        ohlcv[:, 4] /= (float(ohlcv[:, 4].mean()) + 1e-8)

        row = self.data.iloc[self.current_step]
        indicators = np.array(
            [
                self._safe(row, "rsi", 50.0) / 100.0,
                self._safe(row, "macd_histogram", 0.0),
                self._safe(row, "bb_percent_b", 0.5),
                self._safe(row, "ema_trend_num", 0.0),
                self._safe(row, "atr", 0.0) / (norm + 1e-8),
            ],
            dtype=np.float32,
        )

        portfolio_value = self.cash + self.position * last_close
        cash_pct = self.cash / (portfolio_value + 1e-8)
        position_pct = (self.position * last_close) / (portfolio_value + 1e-8)
        drawdown = (self.max_portfolio - portfolio_value) / (self.max_portfolio + 1e-8)
        portfolio_state = np.array([cash_pct, position_pct, drawdown], dtype=np.float32)

        return np.concatenate([ohlcv.flatten(), indicators, portfolio_state]).astype(np.float32)

    def _compute_reward(self, portfolio_value: float, prev_value: float, trade_cost: float) -> float:
        pnl_pct = (portfolio_value - prev_value) / (prev_value + 1e-8) * 100
        drawdown = (self.max_portfolio - portfolio_value) / (self.max_portfolio + 1e-8)
        cost_pct = trade_cost / (prev_value + 1e-8) * 100
        return float(pnl_pct - (0.1 * drawdown * 100) - cost_pct)

    def _get_info(self) -> dict:
        price = float(self.data.iloc[min(self.current_step, len(self.data) - 1)]["close"])
        portfolio_value = self.cash + self.position * price
        win_rate = self.winning_trades / self.total_trades if self.total_trades else 0.0
        return {
            "portfolio_value": portfolio_value,
            "cash": self.cash,
            "position": self.position,
            "total_trades": self.total_trades,
            "win_rate": win_rate,
            "step": self.current_step,
            "episode_start": self.episode_start,
        }

    @staticmethod
    def _safe(row: pd.Series, col: str, default: float) -> float:
        value = row.get(col, default)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        initial_capital: float = 10_000.0,
        **kwargs,
    ) -> "CryptoTradingEnv":
        return cls(pd.read_parquet(str(path)), initial_capital=initial_capital, **kwargs)

    @classmethod
    def train_eval_split(
        cls,
        path: str | Path,
        train_pct: float = 0.80,
        initial_capital: float = 10_000.0,
        **kwargs,
    ) -> tuple["CryptoTradingEnv", "CryptoTradingEnv"]:
        df = pd.read_parquet(str(path))
        split = int(len(df) * train_pct)
        return (
            cls(df.iloc[:split].reset_index(drop=True), initial_capital=initial_capital, **kwargs),
            cls(df.iloc[split:].reset_index(drop=True), initial_capital=initial_capital, **kwargs),
        )

    @classmethod
    def walk_forward_windows(
        cls,
        path: str | Path,
        train_days: int = 180,
        eval_days: int = 30,
        step_days: int = 30,
        timeframe: str = "30m",
        **kwargs,
    ) -> list[tuple["CryptoTradingEnv", "CryptoTradingEnv"]]:
        df = pd.read_parquet(str(path))
        candles_per_day = {"30m": 48, "1h": 24, "4h": 6, "1d": 1}.get(timeframe, 48)
        train_len = train_days * candles_per_day
        eval_len = eval_days * candles_per_day
        step_len = step_days * candles_per_day

        windows = []
        start = 0
        while start + train_len + eval_len <= len(df):
            train_data = df.iloc[start : start + train_len].reset_index(drop=True)
            eval_data = df.iloc[start + train_len : start + train_len + eval_len].reset_index(drop=True)
            windows.append((cls(train_data, **kwargs), cls(eval_data, **kwargs)))
            start += step_len
        return windows
