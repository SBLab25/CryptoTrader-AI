# File: src/risk/engine.py
"""
Risk Management Engine
Validates all trades before execution.
NO trade bypasses risk checks.
"""
from typing import List, Optional
from src.core.models import Trade, TradeSignal, RiskAssessment, Portfolio
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RiskEngine:
    def __init__(self):
        self.max_position_size_pct = settings.max_position_size_pct / 100
        self.stop_loss_pct = settings.stop_loss_pct / 100
        self.take_profit_pct = settings.take_profit_pct / 100
        self.max_daily_loss_pct = settings.max_daily_loss_pct / 100
        self.max_drawdown_pct = settings.max_drawdown_pct / 100
        self.max_open_positions = settings.max_open_positions

        # Daily tracking
        self._daily_pnl = 0.0
        self._peak_portfolio_value = settings.initial_capital
        self._trading_paused = False
        self._pause_reason = ""

    def assess_trade(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        current_open_positions: int,
    ) -> RiskAssessment:
        """
        Full risk assessment before approving a trade.
        Returns RiskAssessment with approved=True/False and reasoning.
        """
        warnings: List[str] = []

        # 1. System pause check
        if self._trading_paused:
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason=f"Trading PAUSED: {self._pause_reason}",
            )

        # 2. Max open positions
        if current_open_positions >= self.max_open_positions:
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason=f"Max open positions reached ({self.max_open_positions})",
            )

        # 3. Confidence threshold
        if signal.confidence < 0.55:
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason=f"Signal confidence too low: {signal.confidence:.2%} (min 55%)",
            )

        # 4. Position sizing
        available = portfolio.available_balance
        max_trade_value = portfolio.total_value * self.max_position_size_pct
        trade_value = min(available * 0.95, max_trade_value)

        if trade_value < 10:
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason="Insufficient available balance for minimum trade size ($10)",
            )

        trade_quantity = trade_value / signal.entry_price

        # 5. Risk/reward ratio
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio < 1.5:
                return RiskAssessment(
                    approved=False,
                    symbol=signal.symbol,
                    trade_size=trade_quantity,
                    risk_amount=risk * trade_quantity,
                    risk_pct=risk / signal.entry_price,
                    reason=f"Risk/Reward ratio too low: {rr_ratio:.2f} (min 1.5)",
                )

        # 6. Stop-loss validation
        if signal.stop_loss <= 0 or signal.take_profit <= 0:
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason="Invalid stop_loss or take_profit levels",
            )

        # 7. Daily loss check
        if self._daily_pnl < -(portfolio.total_value * self.max_daily_loss_pct):
            self._trading_paused = True
            self._pause_reason = f"Daily loss limit exceeded: {self._daily_pnl:.2f}"
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason=self._pause_reason,
            )

        # 8. Drawdown check
        if portfolio.total_value < self._peak_portfolio_value * (1 - self.max_drawdown_pct):
            self._trading_paused = True
            self._pause_reason = f"Max drawdown exceeded"
            return RiskAssessment(
                approved=False,
                symbol=signal.symbol,
                trade_size=0,
                risk_amount=0,
                risk_pct=0,
                reason=self._pause_reason,
            )

        # Warnings (non-blocking)
        if signal.confidence < 0.70:
            warnings.append(f"Moderate confidence: {signal.confidence:.2%}")
        if trade_value > portfolio.total_value * 0.04:
            warnings.append("Large position size relative to portfolio")

        # Update peak
        if portfolio.total_value > self._peak_portfolio_value:
            self._peak_portfolio_value = portfolio.total_value

        risk_amount = risk * trade_quantity
        risk_pct = risk / signal.entry_price

        logger.info(
            f"[RISK] APPROVED {signal.symbol} | Size: {trade_quantity:.6f} | "
            f"Risk: {risk_pct:.2%} | R:R {rr_ratio:.2f}"
        )

        return RiskAssessment(
            approved=True,
            symbol=signal.symbol,
            trade_size=trade_quantity,
            risk_amount=round(risk_amount, 4),
            risk_pct=round(risk_pct, 4),
            warnings=warnings,
        )

    def update_daily_pnl(self, pnl: float):
        self._daily_pnl += pnl

    def reset_daily_pnl(self):
        """Call at start of each trading day"""
        self._daily_pnl = 0.0
        if self._trading_paused and "Daily loss" in self._pause_reason:
            self._trading_paused = False
            self._pause_reason = ""

    def resume_trading(self):
        self._trading_paused = False
        self._pause_reason = ""

    @property
    def is_paused(self) -> bool:
        return self._trading_paused

    def compute_stop_loss(self, entry_price: float, side: str, atr: Optional[float] = None) -> float:
        """Compute dynamic stop-loss using ATR if available"""
        if atr and atr > 0:
            multiplier = 1.5
            if side == "buy":
                return round(entry_price - (atr * multiplier), 8)
            else:
                return round(entry_price + (atr * multiplier), 8)
        else:
            if side == "buy":
                return round(entry_price * (1 - self.stop_loss_pct), 8)
            else:
                return round(entry_price * (1 + self.stop_loss_pct), 8)

    def compute_take_profit(self, entry_price: float, stop_loss: float, side: str, rr: float = 2.0) -> float:
        """Compute take-profit based on risk/reward ratio"""
        risk = abs(entry_price - stop_loss)
        if side == "buy":
            return round(entry_price + (risk * rr), 8)
        else:
            return round(entry_price - (risk * rr), 8)


# Singleton instance
risk_engine = RiskEngine()
