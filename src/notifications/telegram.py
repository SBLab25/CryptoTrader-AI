# File: src/notifications/telegram.py
"""
Notification System
Sends Telegram alerts for trades, signals, risk events, and daily summaries.
Gracefully no-ops if credentials are not configured.
"""
import asyncio
import aiohttp
from typing import Optional
from datetime import datetime

from src.core.models import Trade, TradeSignal, Portfolio, OrderSide
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """
    Sends messages to a Telegram chat via Bot API.
    All methods are safe — they catch and log errors without crashing the system.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = bool(self.token and self.chat_id)
        self._session: Optional[aiohttp.ClientSession] = None

        if self.enabled:
            logger.info("[NOTIFY] Telegram notifications enabled ✓")
        else:
            logger.info("[NOTIFY] Telegram not configured — notifications disabled")

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            )
        return self._session

    async def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a raw message to the configured Telegram chat"""
        if not self.enabled:
            return False
        try:
            session = await self._get_session()
            url = self.BASE_URL.format(token=self.token)
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                logger.warning(f"[NOTIFY] Telegram API error {resp.status}: {body}")
                return False
        except Exception as e:
            logger.error(f"[NOTIFY] Failed to send Telegram message: {e}")
            return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Formatted Alert Methods ───────────────────────────────────────────────

    async def alert_trade_opened(self, trade: Trade) -> None:
        mode = "📄 PAPER" if trade.is_paper else "💰 LIVE"
        side_emoji = "🟢" if trade.side == OrderSide.BUY else "🔴"
        risk = abs(trade.entry_price - trade.stop_loss) * trade.quantity
        reward = abs(trade.take_profit - trade.entry_price) * trade.quantity

        msg = (
            f"<b>{side_emoji} Trade Opened — {mode}</b>\n\n"
            f"📊 Symbol: <code>{trade.symbol}</code>\n"
            f"📈 Side: <b>{trade.side.value.upper()}</b>\n"
            f"💵 Entry: <code>${trade.entry_price:,.4f}</code>\n"
            f"📦 Quantity: <code>{trade.quantity:.6f}</code>\n"
            f"🛑 Stop Loss: <code>${trade.stop_loss:,.4f}</code>\n"
            f"🎯 Take Profit: <code>${trade.take_profit:,.4f}</code>\n"
            f"⚖️ Risk/Reward: <code>${risk:.2f} / ${reward:.2f}</code>\n"
            f"🔧 Strategy: <code>{trade.strategy}</code>\n"
            f"🕐 Time: <code>{trade.created_at.strftime('%H:%M:%S UTC')}</code>"
        )
        await self.send(msg)

    async def alert_trade_closed(self, trade: Trade) -> None:
        pnl = trade.pnl or 0
        pnl_pct = trade.pnl_pct or 0
        result_emoji = "✅ PROFIT" if pnl > 0 else "❌ LOSS"
        mode = "📄 PAPER" if trade.is_paper else "💰 LIVE"

        reason_map = {
            "take_profit": "🎯 Take Profit Hit",
            "stop_loss": "🛑 Stop Loss Hit",
            "manual": "👤 Manual Close",
            "timeout": "⏰ Timeout",
        }
        reason_str = reason_map.get(trade.exit_reason or "", trade.exit_reason or "Unknown")

        msg = (
            f"<b>{result_emoji} — {mode}</b>\n\n"
            f"📊 Symbol: <code>{trade.symbol}</code>\n"
            f"📈 Side: <b>{trade.side.value.upper()}</b>\n"
            f"💵 Entry: <code>${trade.entry_price:,.4f}</code>\n"
            f"💵 Exit: <code>${trade.exit_price:,.4f}</code>\n"
            f"💰 PnL: <code>${pnl:+.4f} ({pnl_pct:+.2f}%)</code>\n"
            f"📌 Reason: {reason_str}\n"
            f"🕐 Duration: <code>{_trade_duration(trade)}</code>"
        )
        await self.send(msg)

    async def alert_strong_signal(self, signal: TradeSignal) -> None:
        """Only sent for STRONG_BUY / STRONG_SELL signals"""
        from src.core.models import SignalStrength
        if signal.signal not in [SignalStrength.STRONG_BUY, SignalStrength.STRONG_SELL]:
            return

        direction = "🚀 STRONG BUY" if signal.signal == SignalStrength.STRONG_BUY else "🔻 STRONG SELL"
        msg = (
            f"<b>{direction} Signal</b>\n\n"
            f"📊 Symbol: <code>{signal.symbol}</code>\n"
            f"🎯 Confidence: <code>{signal.confidence:.0%}</code>\n"
            f"💵 Entry: <code>${signal.entry_price:,.4f}</code>\n"
            f"🛑 Stop Loss: <code>${signal.stop_loss:,.4f}</code>\n"
            f"🎯 Take Profit: <code>${signal.take_profit:,.4f}</code>\n\n"
            f"🧠 <i>{signal.reasoning[:200]}</i>"
        )
        await self.send(msg)

    async def alert_risk_paused(self, reason: str) -> None:
        msg = (
            f"⚠️ <b>Trading PAUSED — Risk Limit Reached</b>\n\n"
            f"Reason: <code>{reason}</code>\n\n"
            f"Use /resume via API or dashboard to re-enable trading."
        )
        await self.send(msg)

    async def alert_daily_summary(self, portfolio: Portfolio, stats: dict) -> None:
        pnl_emoji = "📈" if portfolio.daily_pnl >= 0 else "📉"
        msg = (
            f"<b>{pnl_emoji} Daily Trading Summary</b>\n"
            f"<i>{datetime.utcnow().strftime('%Y-%m-%d UTC')}</i>\n\n"
            f"💼 Portfolio: <code>${portfolio.total_value:,.2f}</code>\n"
            f"📊 Daily PnL: <code>${portfolio.daily_pnl:+.2f} ({portfolio.daily_pnl_pct:+.2f}%)</code>\n"
            f"📈 Total PnL: <code>${portfolio.total_pnl:+.2f} ({portfolio.total_pnl_pct:+.2f}%)</code>\n"
            f"📦 Open Positions: <code>{len(portfolio.open_positions)}</code>\n\n"
            f"📉 Trades Today: <code>{stats.get('total_trades', 0)}</code>\n"
            f"✅ Win Rate: <code>{stats.get('win_rate_pct', 0):.1f}%</code>\n"
            f"💰 Best Trade: <code>${stats.get('avg_win', 0):+.2f}</code>"
        )
        await self.send(msg)

    async def alert_system_start(self, mode: str, symbols: list) -> None:
        msg = (
            f"🤖 <b>Crypto Trading Agent Started</b>\n\n"
            f"Mode: <b>{'📄 PAPER TRADING' if mode == 'paper' else '💰 LIVE TRADING'}</b>\n"
            f"Symbols: <code>{', '.join(symbols)}</code>\n"
            f"Time: <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</code>"
        )
        await self.send(msg)


def _trade_duration(trade: Trade) -> str:
    if not trade.closed_at:
        return "—"
    delta = trade.closed_at - trade.created_at
    mins = int(delta.total_seconds() // 60)
    hrs = mins // 60
    mins = mins % 60
    if hrs > 0:
        return f"{hrs}h {mins}m"
    return f"{mins}m"


# ── Singleton ─────────────────────────────────────────────────────────────────
notifier = TelegramNotifier()
