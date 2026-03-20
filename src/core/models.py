# File: src/core/models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum
import uuid


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SignalStrength(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class TradeSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    signal: SignalStrength
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    entry_price: float
    stop_loss: float
    take_profit: float
    indicators: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ai_analysis: Optional[str] = None


class Trade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    status: OrderStatus = OrderStatus.PENDING
    exchange_order_id: Optional[str] = None

    # Results
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # stop_loss | take_profit | manual | timeout
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    # Metadata
    strategy: str = "ai_driven"
    signal_id: Optional[str] = None
    is_paper: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN]


class Position(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    trade_id: str
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    opened_at: datetime = Field(default_factory=datetime.utcnow)


class MarketData(BaseModel):
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # OHLCV candles (last N candles)
    ohlcv: List[dict] = Field(default_factory=list)


class Portfolio(BaseModel):
    total_value: float
    available_balance: float
    invested_value: float
    total_pnl: float
    total_pnl_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    open_positions: List[Position] = Field(default_factory=list)
    is_paper: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RiskAssessment(BaseModel):
    approved: bool
    symbol: str
    trade_size: float
    risk_amount: float
    risk_pct: float
    reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """Shared state passed between agents in the LangGraph graph"""
    symbols: List[str] = Field(default_factory=list)
    market_data: dict = Field(default_factory=dict)  # symbol -> MarketData
    signals: List[TradeSignal] = Field(default_factory=list)
    approved_trades: List[Trade] = Field(default_factory=list)
    executed_trades: List[Trade] = Field(default_factory=list)
    portfolio: Optional[Portfolio] = None
    errors: List[str] = Field(default_factory=list)
    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
