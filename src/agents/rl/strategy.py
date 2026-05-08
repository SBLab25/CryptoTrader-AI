"""Inference wrapper for trained RL trading policies."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

DIRECTION_MAP = {0: "HOLD", 1: "BUY", 2: "SELL"}
POSITION_SIZES = [0.01, 0.02, 0.03, 0.04, 0.05]


class RLStrategy:
    def __init__(self, model, vec_norm=None, symbol: str = "") -> None:
        self._model = model
        self._vec_norm = vec_norm
        self._symbol = symbol

    @classmethod
    def load(
        cls,
        model_path: str | Path,
        vec_norm_path: Optional[str | Path] = None,
        algorithm: str = "ppo",
        symbol: str = "",
    ) -> "RLStrategy":
        try:
            from stable_baselines3 import A2C, PPO, SAC
            from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "stable-baselines3 is required for RLStrategy.load(). "
                "Install stable-baselines3[extra] to use saved models."
            ) from exc

        model_cls = {"ppo": PPO, "sac": SAC, "a2c": A2C}.get(algorithm.lower(), PPO)
        model = model_cls.load(str(model_path))
        vec_norm = None
        if vec_norm_path and Path(vec_norm_path).exists():
            import pandas as pd

            from src.agents.rl.environment import CryptoTradingEnv

            dummy = pd.DataFrame(
                {
                    "open": [1.0] * 250,
                    "high": [1.0] * 250,
                    "low": [1.0] * 250,
                    "close": [1.0] * 250,
                    "volume": [1.0] * 250,
                    "rsi": [50.0] * 250,
                    "macd_histogram": [0.0] * 250,
                    "bb_percent_b": [0.5] * 250,
                    "ema_trend_num": [0.0] * 250,
                    "atr": [0.0] * 250,
                }
            )
            dummy_env = DummyVecEnv([lambda: CryptoTradingEnv(dummy)])
            vec_norm = VecNormalize.load(str(vec_norm_path), dummy_env)
            vec_norm.training = False
        return cls(model=model, vec_norm=vec_norm, symbol=symbol)

    def predict(
        self,
        indicators: dict,
        ohlcv: list[dict],
        portfolio: dict,
        deterministic: bool = True,
    ) -> Optional[dict]:
        if self._model is None:
            return None

        obs = self._build_observation(indicators, ohlcv, portfolio)
        if obs is None:
            return None

        if self._vec_norm is not None:
            obs = self._vec_norm.normalize_obs(obs.reshape(1, -1))[0]

        action, _ = self._model.predict(obs, deterministic=deterministic)
        direction_idx = int(action[0])
        size_idx = int(action[1])
        direction = DIRECTION_MAP[direction_idx]
        size_pct = POSITION_SIZES[size_idx]
        confidence = self._compute_confidence(obs, direction_idx)

        if direction == "HOLD":
            return {
                "action": "HOLD",
                "confidence": float(confidence),
                "stop_loss": None,
                "take_profit": None,
                "reasoning": f"RL agent: HOLD (confidence {confidence:.2f})",
                "model": "rl_agent",
            }

        current_price = float(ohlcv[-1]["close"]) if ohlcv else 0.0
        atr = indicators.get("atr", current_price * 0.02) or current_price * 0.02
        if direction == "BUY":
            stop_loss = current_price - 1.5 * atr
            take_profit = current_price + 3.0 * atr
        else:
            stop_loss = current_price + 1.5 * atr
            take_profit = current_price - 3.0 * atr

        return {
            "action": direction,
            "confidence": float(confidence),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "size_pct": size_pct,
            "reasoning": (
                f"RL agent ({self._model.__class__.__name__}): {direction} "
                f"at {current_price:.2f}, size={size_pct*100:.0f}%, confidence={confidence:.2f}"
            ),
            "model": "rl_agent",
        }

    def _build_observation(self, indicators: dict, ohlcv: list[dict], portfolio: dict) -> Optional[np.ndarray]:
        if len(ohlcv) < 20:
            return None

        window = ohlcv[-20:]
        try:
            prices = np.array(
                [[c["open"], c["high"], c["low"], c["close"], c["volume"]] for c in window],
                dtype=np.float32,
            )
        except (KeyError, TypeError):
            return None

        last_close = prices[-1, 3]
        norm = last_close if last_close > 0 else 1.0
        prices[:, :4] /= norm
        prices[:, 4] /= (float(prices[:, 4].mean()) + 1e-8)

        indicator_vec = np.array(
            [
                self._safe(indicators, "rsi", 50.0) / 100.0,
                self._safe(indicators, "macd_histogram", 0.0),
                self._safe(indicators, "bb_percent_b", 0.5),
                self._safe(indicators, "ema_trend_num", 0.0),
                self._safe(indicators, "atr", 0.0) / (norm + 1e-8),
            ],
            dtype=np.float32,
        )

        total_value = float(portfolio.get("total_value", 10_000.0))
        cash_balance = float(
            portfolio.get("cash_balance", portfolio.get("available_balance", total_value))
        )
        drawdown = float(portfolio.get("max_drawdown", 0.0) or 0.0)
        position_value = total_value - cash_balance
        port_vec = np.array(
            [
                cash_balance / (total_value + 1e-8),
                position_value / (total_value + 1e-8),
                drawdown,
            ],
            dtype=np.float32,
        )
        return np.concatenate([prices.flatten(), indicator_vec, port_vec]).astype(np.float32)

    def _compute_confidence(self, obs: np.ndarray, chosen_idx: int) -> float:
        try:
            obs_tensor = self._model.policy.obs_to_tensor(obs.reshape(1, -1))[0]
            dist = self._model.policy.get_distribution(obs_tensor)
            probs = dist.distribution.probs.detach().cpu().numpy()[0]
            raw_prob = float(probs[chosen_idx])
            return min(0.5 + raw_prob * 0.45, 0.95)
        except Exception:
            return 0.65

    @staticmethod
    def _safe(values: dict, key: str, default: float) -> float:
        value = values.get(key, default)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)

    def info(self) -> dict:
        return {
            "algorithm": self._model.__class__.__name__ if self._model is not None else None,
            "symbol": self._symbol,
            "has_vecnorm": self._vec_norm is not None,
        }
