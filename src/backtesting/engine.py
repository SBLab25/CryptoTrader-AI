# File: src/backtesting/engine.py
"""
Backtesting Engine
Replay historical OHLCV data through the strategy and risk engine
to evaluate performance before live trading.

Usage:
    engine = BacktestEngine(initial_capital=10000)
    results = engine.run(ohlcv, strategy="momentum", symbol="BTC_USDT")
    print(results.summary())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime

from src.strategies.strategies import (
    momentum_strategy,
    mean_reversion_strategy,
    breakout_strategy,
    select_best_strategy,
    StrategyResult,
)
from src.exchange.indicators import compute_atr
from src.utils.logger import get_logger

logger = get_logger(__name__)

STRATEGY_MAP = {
    "momentum": momentum_strategy,
    "mean_reversion": mean_reversion_strategy,
    "breakout": breakout_strategy,
    "best": select_best_strategy,
}


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    symbol: str
    side: str
    entry_idx: int
    exit_idx: int
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    strategy: str


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    # ── Computed metrics ───────────────────────────────────────────

    @property
    def total_return_pct(self) -> float:
        return round((self.final_capital - self.initial_capital) / self.initial_capital * 100, 2)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl <= 0)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return round(self.winning_trades / self.total_trades * 100, 2)

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        return round(sum(wins) / len(wins), 4) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self.trades if t.pnl <= 0]
        return round(sum(losses) / len(losses), 4) if losses else 0.0

    @property
    def profit_factor(self) -> Optional[float]:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if gross_loss == 0:
            return None
        return round(gross_profit / gross_loss, 2)

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for value in self.equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    @property
    def sharpe_ratio(self) -> Optional[float]:
        """Annualised Sharpe (assumes daily returns, risk-free = 0)"""
        if len(self.equity_curve) < 2:
            return None
        returns = [
            (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
            for i in range(1, len(self.equity_curve))
        ]
        if not returns:
            return None
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(variance)
        if std_r == 0:
            return None
        daily_sharpe = mean_r / std_r
        return round(daily_sharpe * math.sqrt(252), 2)  # annualise

    @property
    def best_trade(self) -> Optional[BacktestTrade]:
        return max(self.trades, key=lambda t: t.pnl) if self.trades else None

    @property
    def worst_trade(self) -> Optional[BacktestTrade]:
        return min(self.trades, key=lambda t: t.pnl) if self.trades else None

    @property
    def avg_holding_bars(self) -> float:
        if not self.trades:
            return 0.0
        return round(sum(t.exit_idx - t.entry_idx for t in self.trades) / len(self.trades), 1)

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "period": f"{self.start_date} → {self.end_date}",
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "avg_holding_bars": self.avg_holding_bars,
            "best_trade_pnl": round(self.best_trade.pnl, 4) if self.best_trade else None,
            "worst_trade_pnl": round(self.worst_trade.pnl, 4) if self.worst_trade else None,
        }

    def print_report(self) -> None:
        s = self.summary()
        print("\n" + "=" * 55)
        print(f"  BACKTEST REPORT — {s['symbol']} [{s['strategy'].upper()}]")
        print("=" * 55)
        print(f"  Period:          {s['period']}")
        print(f"  Timeframe:       {s['timeframe']}")
        print(f"  Initial Capital: ${s['initial_capital']:,.2f}")
        print(f"  Final Capital:   ${s['final_capital']:,.2f}")
        print(f"  Total Return:    {s['total_return_pct']:+.2f}%")
        print("-" * 55)
        print(f"  Total Trades:    {s['total_trades']}")
        print(f"  Win Rate:        {s['win_rate_pct']:.1f}%")
        print(f"  Avg Win:         ${s['avg_win']:+.2f}")
        print(f"  Avg Loss:        ${s['avg_loss']:+.2f}")
        print(f"  Profit Factor:   {s['profit_factor'] or 'N/A'}")
        print(f"  Max Drawdown:    {s['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe Ratio:    {s['sharpe_ratio'] or 'N/A'}")
        print(f"  Avg Hold (bars): {s['avg_holding_bars']}")
        print("=" * 55 + "\n")


# ── Backtest Engine ───────────────────────────────────────────────────────────

class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.05,   # 5% of capital per trade
        max_open_positions: int = 3,
        min_confidence: float = 0.55,
        commission_pct: float = 0.001,      # 0.1% per trade
    ):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.max_open_positions = max_open_positions
        self.min_confidence = min_confidence
        self.commission_pct = commission_pct

    def run(
        self,
        ohlcv: List[dict],
        strategy: str = "momentum",
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
        lookback: int = 50,
    ) -> BacktestResult:
        """
        Run backtest over OHLCV data.

        Args:
            ohlcv: List of candles {timestamp, open, high, low, close, volume}
            strategy: "momentum" | "mean_reversion" | "breakout" | "best"
            symbol: Symbol name for reporting
            timeframe: Timeframe string (display only)
            lookback: Minimum candles required before generating first signal
        """
        strategy_fn = STRATEGY_MAP.get(strategy, select_best_strategy)

        capital = float(self.initial_capital)
        open_positions: List[dict] = []
        closed_trades: List[BacktestTrade] = []
        equity_curve: List[float] = [capital]

        start_ts = ohlcv[lookback]["timestamp"] if len(ohlcv) > lookback else ohlcv[0]["timestamp"]
        end_ts = ohlcv[-1]["timestamp"]

        def ts_to_date(ts: int) -> str:
            try:
                return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            except Exception:
                return str(ts)

        logger.info(
            f"[BACKTEST] Starting: {symbol} | {strategy} | "
            f"{len(ohlcv)} candles | capital=${capital:,.2f}"
        )

        for i in range(lookback, len(ohlcv)):
            candle = ohlcv[i]
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]

            # ── Check open positions for SL/TP hits ──────────────────────────
            still_open = []
            for pos in open_positions:
                hit_tp = (pos["side"] == "buy" and high >= pos["take_profit"]) or \
                         (pos["side"] == "sell" and low <= pos["take_profit"])
                hit_sl = (pos["side"] == "buy" and low <= pos["stop_loss"]) or \
                         (pos["side"] == "sell" and high >= pos["stop_loss"])

                if hit_tp or hit_sl:
                    exit_price = pos["take_profit"] if hit_tp else pos["stop_loss"]
                    exit_reason = "take_profit" if hit_tp else "stop_loss"
                    qty = pos["quantity"]

                    if pos["side"] == "buy":
                        pnl = (exit_price - pos["entry_price"]) * qty
                    else:
                        pnl = (pos["entry_price"] - exit_price) * qty

                    commission = exit_price * qty * self.commission_pct
                    pnl -= commission
                    capital += pnl
                    pnl_pct = pnl / (pos["entry_price"] * qty) * 100

                    closed_trades.append(BacktestTrade(
                        symbol=symbol,
                        side=pos["side"],
                        entry_idx=pos["entry_idx"],
                        exit_idx=i,
                        entry_price=pos["entry_price"],
                        exit_price=exit_price,
                        stop_loss=pos["stop_loss"],
                        take_profit=pos["take_profit"],
                        quantity=qty,
                        pnl=round(pnl, 4),
                        pnl_pct=round(pnl_pct, 2),
                        exit_reason=exit_reason,
                        strategy=strategy,
                    ))
                else:
                    still_open.append(pos)

            open_positions = still_open

            # ── Generate signal on this candle ───────────────────────────────
            if len(open_positions) >= self.max_open_positions:
                equity_curve.append(capital)
                continue

            window = ohlcv[max(0, i - lookback):i + 1]
            atr = compute_atr(window)
            result: Optional[StrategyResult] = strategy_fn(window, close, atr)

            if result and result.is_actionable and result.confidence >= self.min_confidence:
                trade_value = capital * self.position_size_pct
                if trade_value >= 10:
                    qty = trade_value / close
                    commission = close * qty * self.commission_pct
                    capital -= commission  # Entry commission

                    open_positions.append({
                        "side": result.direction,
                        "entry_price": close,
                        "stop_loss": result.stop_loss,
                        "take_profit": result.take_profit,
                        "quantity": qty,
                        "entry_idx": i,
                        "strategy": strategy,
                    })

            equity_curve.append(capital)

        # Close any remaining open positions at last close
        last_close = ohlcv[-1]["close"]
        for pos in open_positions:
            qty = pos["quantity"]
            if pos["side"] == "buy":
                pnl = (last_close - pos["entry_price"]) * qty
            else:
                pnl = (pos["entry_price"] - last_close) * qty
            commission = last_close * qty * self.commission_pct
            pnl -= commission
            capital += pnl
            pnl_pct = pnl / (pos["entry_price"] * qty) * 100

            closed_trades.append(BacktestTrade(
                symbol=symbol,
                side=pos["side"],
                entry_idx=pos["entry_idx"],
                exit_idx=len(ohlcv) - 1,
                entry_price=pos["entry_price"],
                exit_price=last_close,
                stop_loss=pos["stop_loss"],
                take_profit=pos["take_profit"],
                quantity=qty,
                pnl=round(pnl, 4),
                pnl_pct=round(pnl_pct, 2),
                exit_reason="end_of_data",
                strategy=strategy,
            ))

        equity_curve.append(capital)

        result = BacktestResult(
            symbol=symbol,
            strategy=strategy,
            timeframe=timeframe,
            start_date=ts_to_date(start_ts),
            end_date=ts_to_date(end_ts),
            initial_capital=float(self.initial_capital),
            final_capital=float(round(capital, 4)),
            trades=closed_trades,
            equity_curve=equity_curve,
        )

        logger.info(
            f"[BACKTEST] Complete: {result.total_trades} trades | "
            f"Win rate: {result.win_rate:.1f}% | "
            f"Return: {result.total_return_pct:+.2f}% | "
            f"Max DD: {result.max_drawdown_pct:.2f}%"
        )

        return result


# ── Multi-Strategy Comparison ─────────────────────────────────────────────────

def compare_strategies(
    ohlcv: List[dict],
    symbol: str = "UNKNOWN",
    initial_capital: float = 10000.0,
) -> Dict[str, BacktestResult]:
    """Run all strategies on the same dataset and return comparison"""
    engine = BacktestEngine(initial_capital=initial_capital)
    results = {}
    for strategy_name in ["momentum", "mean_reversion", "breakout", "best"]:
        results[strategy_name] = engine.run(ohlcv, strategy=strategy_name, symbol=symbol)
    return results
