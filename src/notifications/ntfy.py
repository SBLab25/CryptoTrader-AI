"""Ntfy notification helpers for local/self-hosted push delivery."""

from __future__ import annotations

from typing import Optional

import httpx

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TAGS = {
    "trade_buy": "chart_increasing,green_circle",
    "trade_sell": "chart_decreasing,red_circle",
    "trade_win": "white_check_mark,moneybag",
    "trade_loss": "x,chart_with_downwards_trend",
    "approval": "bell,rotating_light",
    "circuit": "electric_plug",
    "summary": "bar_chart",
    "system": "gear",
}


async def send_notification(
    title: str,
    message: str,
    priority: int = 3,
    tags: Optional[str] = None,
    click: Optional[str] = None,
) -> bool:
    if not settings.ntfy_url or not settings.ntfy_topic:
        return False

    headers = {"Title": title, "Priority": str(priority), "Content-Type": "text/plain"}
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}",
                headers=headers,
                content=message.encode("utf-8"),
            )
            return response.status_code in (200, 201)
    except Exception as exc:
        logger.warning(f"[NTFY] Notification send failed: {exc}")
        return False


async def notify_trade_opened(
    symbol: str,
    side: str,
    entry_price: float,
    stop_loss: Optional[float],
    take_profit: Optional[float],
    confidence: float,
    position_usd: float,
    strategy: str,
) -> None:
    buy = side.upper() == "BUY"
    await send_notification(
        title=f"{side.upper()} {symbol}",
        message=(
            f"Strategy: {strategy}\n"
            f"Entry: {entry_price:.4f} USDT\n"
            f"Size: ${position_usd:.2f}\n"
            f"Stop Loss: {stop_loss if stop_loss is not None else '-'}\n"
            f"Take Profit: {take_profit if take_profit is not None else '-'}\n"
            f"Confidence: {confidence:.0%}"
        ),
        priority=4,
        tags=_TAGS["trade_buy"] if buy else _TAGS["trade_sell"],
    )


async def notify_trade_closed(
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    pnl_pct: float,
    pnl_usd: float,
) -> None:
    won = pnl_pct > 0
    await send_notification(
        title=f"{'WIN' if won else 'LOSS'} {symbol}",
        message=(
            f"Direction: {side.upper()}\n"
            f"Entry: {entry_price:.4f}\n"
            f"Exit: {exit_price:.4f}\n"
            f"PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f})"
        ),
        priority=4,
        tags=_TAGS["trade_win"] if won else _TAGS["trade_loss"],
    )


async def notify_approval_requested(
    symbol: str,
    side: str,
    position_usd: float,
    confidence: float,
    approval_id: str,
    expires_in_s: int,
) -> None:
    await send_notification(
        title=f"APPROVAL NEEDED {symbol}",
        message=(
            f"Side: {side.upper()}\n"
            f"Size: ${position_usd:.2f}\n"
            f"Confidence: {confidence:.0%}\n"
            f"Approval ID: {approval_id}\n"
            f"Expires in: {expires_in_s}s"
        ),
        priority=5,
        tags=_TAGS["approval"],
    )


async def notify_circuit_open(exchange: str) -> None:
    await send_notification(
        title=f"Circuit Breaker OPEN - {exchange}",
        message=f"Exchange '{exchange}' is unreachable. Live trading suspended.",
        priority=5,
        tags=_TAGS["circuit"],
    )


async def notify_circuit_closed(exchange: str) -> None:
    await send_notification(
        title=f"Exchange Recovered - {exchange}",
        message=f"Exchange '{exchange}' is reachable again. Live trading resumed.",
        priority=3,
        tags=_TAGS["circuit"],
    )


async def notify_daily_summary(
    total_trades: int,
    win_rate: float,
    daily_pnl: float,
    portfolio_value: float,
) -> None:
    await send_notification(
        title="Daily Summary",
        message=(
            f"Trades: {total_trades}\n"
            f"Win Rate: {win_rate:.1%}\n"
            f"Daily PnL: ${daily_pnl:+.2f}\n"
            f"Portfolio: ${portfolio_value:,.2f}"
        ),
        priority=2,
        tags=_TAGS["summary"],
    )


async def notify_test() -> bool:
    return await send_notification(
        title="CryptoTrader-AI Test",
        message="Notifications are working correctly.",
        priority=1,
        tags=_TAGS["system"],
    )
