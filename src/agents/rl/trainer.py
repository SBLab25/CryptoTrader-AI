"""Training helpers for PPO/SAC/A2C based crypto agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.agents.rl.environment import CryptoTradingEnv


class RLTrainer:
    def __init__(
        self,
        algorithm: str = "ppo",
        initial_capital: float = 10_000.0,
        checkpoint_dir: str | Path = "training/checkpoints",
    ) -> None:
        self.algorithm = algorithm.lower()
        self.initial_capital = initial_capital
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _load_sb3(self):
        try:
            from stable_baselines3 import A2C, PPO, SAC
            from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "stable-baselines3 is required for RL training. "
                "Install stable-baselines3[extra] to use RLTrainer."
            ) from exc
        return {"ppo": PPO, "sac": SAC, "a2c": A2C}, DummyVecEnv, VecNormalize

    def _hyperparams(self, dataset_size: int) -> dict[str, Any]:
        if self.algorithm == "sac":
            return {
                "learning_rate": 3e-4,
                "buffer_size": max(1_000, dataset_size * 5),
                "batch_size": min(256, max(32, dataset_size // 10 or 32)),
                "gamma": 0.99,
                "tau": 0.005,
            }

        if self.algorithm == "a2c":
            return {
                "learning_rate": 7e-4,
                "n_steps": min(512, max(32, dataset_size)),
                "gamma": 0.99,
                "gae_lambda": 1.0,
            }

        return {
            "learning_rate": 3e-4,
            "n_steps": min(2048, max(32, dataset_size)),
            "batch_size": min(256, max(32, dataset_size // 8 or 32)),
            "n_epochs": 10,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_range": 0.2,
        }

    def train(
        self,
        parquet_path: str | Path,
        total_timesteps: int = 50_000,
        model_name: Optional[str] = None,
    ) -> dict[str, Any]:
        model_classes, DummyVecEnv, VecNormalize = self._load_sb3()
        train_env, eval_env = CryptoTradingEnv.train_eval_split(
            parquet_path,
            initial_capital=self.initial_capital,
        )
        dataset_size = len(train_env.data)
        hyperparams = self._hyperparams(dataset_size)

        vec_env = DummyVecEnv([lambda: train_env])
        vec_env = VecNormalize(vec_env, norm_obs=True, norm_reward=True)

        model_cls = model_classes.get(self.algorithm, model_classes["ppo"])
        model = model_cls("MlpPolicy", vec_env, verbose=0, **hyperparams)
        model.learn(total_timesteps=total_timesteps)

        name = model_name or f"{self.algorithm}_{Path(parquet_path).stem}"
        output_dir = self.checkpoint_dir / name
        output_dir.mkdir(parents=True, exist_ok=True)

        model_path = output_dir / "best_model.zip"
        stats_path = output_dir / "vec_normalize.pkl"
        model.save(str(model_path))
        vec_env.save(str(stats_path))

        metrics = self.evaluate(model=model, env=eval_env)
        return {
            "model_path": model_path,
            "vec_norm_path": stats_path,
            "metrics": metrics,
            "hyperparams": hyperparams,
        }

    def evaluate(self, model=None, env: Optional[CryptoTradingEnv] = None, episodes: int = 1) -> dict[str, Any]:
        if model is None or env is None:
            return {"episodes": 0, "avg_reward": 0.0, "final_portfolio": self.initial_capital}

        rewards = []
        finals = []
        for _ in range(episodes):
            obs, _ = env.reset()
            done = False
            truncated = False
            total_reward = 0.0
            info = {}
            while not done and not truncated:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, done, truncated, info = env.step(action)
                total_reward += reward
            rewards.append(total_reward)
            finals.append(info.get("portfolio_value", self.initial_capital))

        avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
        avg_final = sum(finals) / len(finals) if finals else self.initial_capital
        return {
            "episodes": len(rewards),
            "avg_reward": avg_reward,
            "final_portfolio": avg_final,
        }
