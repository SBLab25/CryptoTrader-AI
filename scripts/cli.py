# File: scripts/cli.py
#!/usr/bin/env python3
"""
CLI Tool for the Crypto Trading Agent
Usage: python scripts/cli.py [command] [options]

Commands:
  status          Show system status
  backtest        Run a backtest
  symbols         List monitored symbols
  positions       Show open positions
  performance     Show performance stats
  resume          Resume paused trading
  stop            Stop trading loop
  start           Start trading loop
"""
import sys
import asyncio
import json
import argparse
import aiohttp

API_BASE = "http://localhost:8000"


async def api(session, method, path, data=None):
    url = f"{API_BASE}{path}"
    try:
        if method == "GET":
            async with session.get(url) as r:
                return await r.json()
        else:
            async with session.post(url, json=data) as r:
                return await r.json()
    except Exception as e:
        print(f"❌ API error: {e}")
        return None


def print_section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


async def cmd_status(session, args):
    r = await api(session, "GET", "/api/status")
    if not r:
        return
    print_section("System Status")
    print(f"  Mode:            {r.get('mode', '?').upper()}")
    print(f"  Running:         {'✅ Yes' if r.get('is_running') else '❌ No'}")
    print(f"  Cycle count:     {r.get('cycle_count', 0)}")
    print(f"  Open positions:  {r.get('open_positions', 0)}")
    print(f"  Risk paused:     {'⚠️  YES' if r.get('trading_paused') else 'No'}")
    print(f"  Last cycle:      {r.get('last_cycle_at', '—')}")
    print(f"  Symbols:         {', '.join(r.get('symbols', []))}")

    p = r.get('performance', {})
    if p and p.get('total_trades', 0) > 0:
        print_section("Performance")
        print(f"  Total trades:    {p['total_trades']}")
        print(f"  Win rate:        {p.get('win_rate_pct', 0):.1f}%")
        print(f"  Total PnL:       ${p.get('total_pnl', 0):+.4f}")
        print(f"  Profit factor:   {p.get('profit_factor', '—')}")


async def cmd_positions(session, args):
    r = await api(session, "GET", "/api/positions")
    if not r:
        return
    print_section(f"Open Positions ({len(r)})")
    if not r:
        print("  No open positions")
        return
    for p in r:
        pnl = p.get('unrealized_pnl', 0)
        sign = "+" if pnl >= 0 else ""
        print(f"  {p['symbol']:12} {p['side'].upper():4}  "
              f"qty={p['quantity']:.6f}  entry={p['entry_price']:.4f}  "
              f"current={p['current_price']:.4f}  "
              f"pnl={sign}${pnl:.4f} ({sign}{p.get('unrealized_pnl_pct', 0):.2f}%)")


async def cmd_performance(session, args):
    r = await api(session, "GET", "/api/performance")
    if not r or r.get("message"):
        print("\n  No closed trades yet.")
        return
    print_section("Performance Statistics")
    print(f"  Total trades:    {r['total_trades']}")
    print(f"  Winning trades:  {r['winning_trades']}")
    print(f"  Win rate:        {r['win_rate_pct']:.2f}%")
    print(f"  Total PnL:       ${r['total_pnl']:+.4f}")
    print(f"  Avg win:         ${r['avg_win']:+.4f}")
    print(f"  Avg loss:        ${r['avg_loss']:+.4f}")
    print(f"  Profit factor:   {r.get('profit_factor', '—')}")
    print(f"  Max win:         ${r.get('max_win', 0):+.4f}")
    print(f"  Max loss:        ${r.get('max_loss', 0):+.4f}")


async def cmd_backtest(session, args):
    print_section(f"Running Backtest: {args.strategy} on {args.trend} market")
    payload = {
        "symbol": args.symbol,
        "strategy": args.strategy,
        "initial_capital": args.capital,
    }
    r = await api(session, "POST", "/api/backtest", payload)
    if not r:
        return
    sign = "+" if r['total_return_pct'] >= 0 else ""
    print(f"  Symbol:          {r['symbol']}")
    print(f"  Strategy:        {r['strategy']}")
    print(f"  Total Return:    {sign}{r['total_return_pct']:.2f}%")
    print(f"  Total Trades:    {r['total_trades']}")
    print(f"  Win Rate:        {r['win_rate_pct']:.2f}%")
    print(f"  Profit Factor:   {r.get('profit_factor', '—')}")
    print(f"  Max Drawdown:    {r['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe Ratio:    {r.get('sharpe_ratio', '—')}")
    print(f"  Final Capital:   ${r['final_capital']:,.2f}")


async def cmd_resume(session, args):
    r = await api(session, "POST", "/api/risk/resume")
    print("\n  ▶ Trading resumed" if r else "\n  ❌ Failed to resume")


async def cmd_stop(session, args):
    r = await api(session, "POST", "/api/trading/stop")
    print("\n  ⏹ Trading stopped" if r else "\n  ❌ Failed to stop")


async def cmd_start(session, args):
    r = await api(session, "POST", "/api/trading/start")
    print(f"\n  🚀 {r.get('status', 'unknown')}" if r else "\n  ❌ Failed to start")


COMMANDS = {
    "status": cmd_status,
    "positions": cmd_positions,
    "performance": cmd_performance,
    "backtest": cmd_backtest,
    "resume": cmd_resume,
    "stop": cmd_stop,
    "start": cmd_start,
}


async def main():
    parser = argparse.ArgumentParser(
        description="Crypto Trading Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("command", choices=list(COMMANDS.keys()), help="Command to run")
    parser.add_argument("--symbol", default="BTC_USDT", help="Symbol for backtest")
    parser.add_argument("--strategy", default="best",
                        choices=["momentum", "mean_reversion", "breakout", "best"],
                        help="Strategy for backtest")
    parser.add_argument("--trend", default="up",
                        choices=["up", "down", "ranging", "volatile"],
                        help="Market type for backtest simulation")
    parser.add_argument("--capital", type=float, default=10000.0, help="Capital for backtest")
    parser.add_argument("--host", default="localhost:8000", help="API host")

    args = parser.parse_args()

    global API_BASE
    API_BASE = f"http://{args.host}"

    async with aiohttp.ClientSession() as session:
        fn = COMMANDS[args.command]
        await fn(session, args)
    print()


if __name__ == "__main__":
    asyncio.run(main())
