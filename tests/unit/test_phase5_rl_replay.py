import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.agents.rl.environment import CryptoTradingEnv
from src.agents.rl.strategy import RLStrategy
from src.agents.rl.trainer import RLTrainer
from src.exchange.replay_engine import ReplayEngine
from training.data.download_historical import _atr, _ema_series, _rsi, precompute_indicators


@pytest.fixture
def sample_ohlcv_df():
    count = 250
    rng = np.random.default_rng(42)
    closes = 67_000 + np.cumsum(rng.normal(0, 200, count))
    closes = np.clip(closes, 10_000, 200_000)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=count, freq="30min", tz="UTC"),
            "symbol": "BTC_USDT",
            "open": closes * (1 - rng.uniform(0, 0.001, count)),
            "high": closes * (1 + rng.uniform(0, 0.002, count)),
            "low": closes * (1 - rng.uniform(0, 0.002, count)),
            "close": closes,
            "volume": rng.uniform(5, 50, count),
            "rsi": rng.uniform(25, 75, count),
            "macd_histogram": rng.normal(0, 0.05, count),
            "bb_percent_b": rng.uniform(0, 1, count),
            "ema_trend_num": rng.choice([-1.0, 0.0, 1.0], count),
            "atr": rng.uniform(300, 800, count),
            "volume_ratio": rng.uniform(0.5, 2.5, count),
        }
    )


def test_env_observation_shape(sample_ohlcv_df):
    env = CryptoTradingEnv(data=sample_ohlcv_df, initial_capital=10_000.0, seed=42)
    obs, info = env.reset()
    assert obs.shape == (108,)
    assert obs.dtype == np.float32
    assert info["portfolio_value"] == pytest.approx(10_000.0)


def test_env_buy_and_sell_flow(sample_ohlcv_df):
    env = CryptoTradingEnv(data=sample_ohlcv_df, initial_capital=10_000.0, seed=42)
    env.reset()
    cash_before = env.cash
    env.step([1, 2])
    assert env.cash < cash_before
    assert env.position > 0
    _, reward, _, _, info = env.step([2, 0])
    assert env.position == 0.0
    assert isinstance(reward, float)
    assert info["total_trades"] == 2


def test_train_eval_and_walk_forward(tmp_path, sample_ohlcv_df):
    path = tmp_path / "sample.parquet"
    sample_ohlcv_df.to_parquet(path, index=False)

    train_env, eval_env = CryptoTradingEnv.train_eval_split(path, train_pct=0.8)
    assert len(train_env.data) + len(eval_env.data) == len(sample_ohlcv_df)
    assert set(train_env.data["timestamp"].astype(str)).isdisjoint(set(eval_env.data["timestamp"].astype(str)))

    windows = CryptoTradingEnv.walk_forward_windows(path, train_days=2, eval_days=1, step_days=1, timeframe="30m")
    assert windows


def test_indicator_helpers_and_precompute(tmp_path):
    closes = np.linspace(60_000, 70_000, 100)
    highs = closes * 1.002
    lows = closes * 0.998

    assert _ema_series(closes, period=20).shape == closes.shape
    assert np.all((_rsi(closes, period=14)[~np.isnan(_rsi(closes, period=14))] >= 0))
    valid_atr = _atr(highs, lows, closes, period=14)
    assert np.all(valid_atr[~np.isnan(valid_atr)] >= 0)

    count = 250
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=count, freq="30min", tz="UTC"),
            "symbol": "BTC_USDT",
            "open": closes[:count] if len(closes) >= count else np.linspace(60_000, 70_000, count),
            "high": np.linspace(60_100, 70_100, count),
            "low": np.linspace(59_900, 69_900, count),
            "close": np.linspace(60_000, 70_000, count),
            "volume": np.linspace(10, 50, count),
        }
    )
    path = tmp_path / "history.parquet"
    df.to_parquet(path, index=False)
    precompute_indicators(path)
    result = pd.read_parquet(path)
    for column in ["rsi", "macd_histogram", "bb_percent_b", "ema_trend_num", "atr", "volume_ratio"]:
        assert column in result.columns
    assert result.isnull().sum().sum() == 0


def test_replay_engine_merge_and_interval(tmp_path, sample_ohlcv_df):
    paths = {}
    for symbol in ["BTC_USDT", "ETH_USDT"]:
        path = tmp_path / f"{symbol}_30m_365d.parquet"
        frame = sample_ohlcv_df.copy()
        frame["symbol"] = symbol
        frame.to_parquet(path, index=False)
        paths[symbol] = path

    engine = ReplayEngine(data_paths=paths, speed_multiplier=100.0, timeframe="30m", persist_to_db=False)
    merged = engine._load_and_merge()
    assert len(merged) == 500
    assert abs(engine._replay_interval - 18.0) < 0.01
    assert (merged["timestamp"].values[1:] >= merged["timestamp"].values[:-1]).all()


@pytest.mark.asyncio
async def test_replay_engine_publishes_ticks(tmp_path, sample_ohlcv_df):
    path = tmp_path / "BTC_USDT_30m_365d.parquet"
    sample_ohlcv_df.to_parquet(path, index=False)
    engine = ReplayEngine(
        data_paths={"BTC_USDT": path},
        speed_multiplier=100_000.0,
        persist_to_db=False,
    )

    published = []

    async def capture(tick):
        published.append(tick)

    with patch("src.exchange.replay_engine.publish_tick", capture):
        await engine.run()

    assert len(published) == len(sample_ohlcv_df)
    assert published[0]["source"] == "replay"


def test_rl_strategy_builds_observation_and_signal():
    indicators = {
        "rsi": 32.5,
        "macd_histogram": 0.045,
        "bb_percent_b": 0.18,
        "ema_trend_num": 1.0,
        "atr": 420.0,
    }
    ohlcv = [
        {"timestamp": i, "open": 67_000 + i * 10, "high": 67_100 + i * 10, "low": 66_900 + i * 10, "close": 67_050 + i * 10, "volume": 10.0}
        for i in range(25)
    ]
    portfolio = {"total_value": 10_500.0, "cash_balance": 5_000.0, "max_drawdown": 0.02}

    model = MagicMock()
    model.predict = MagicMock(return_value=(np.array([1, 2]), None))
    strategy = RLStrategy(model=model, symbol="BTC_USDT")
    obs = strategy._build_observation(indicators, ohlcv, portfolio)
    assert obs is not None
    assert obs.shape == (108,)

    with patch.object(strategy, "_compute_confidence", return_value=0.78):
        signal = strategy.predict(indicators, ohlcv, portfolio)
    assert signal["action"] == "BUY"
    assert signal["stop_loss"] < ohlcv[-1]["close"]
    assert signal["take_profit"] > ohlcv[-1]["close"]


def test_rl_trainer_hyperparams():
    trainer = RLTrainer()
    ppo = trainer._hyperparams(10_000)
    for key in ["learning_rate", "n_steps", "batch_size", "n_epochs", "gamma"]:
        assert key in ppo
    trainer.algorithm = "sac"
    sac = trainer._hyperparams(10_000)
    for key in ["learning_rate", "buffer_size", "batch_size", "gamma"]:
        assert key in sac
    trainer.algorithm = "ppo"
    small = trainer._hyperparams(100)
    assert small["n_steps"] <= 100
