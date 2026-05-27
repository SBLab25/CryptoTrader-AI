"use client";

import { useState } from "react";
import useSWR from "swr";

import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EquityChart } from "@/components/charts/EquityChart";
import { PositionsTable } from "@/components/ui/PositionsTable";
import { RiskPanel } from "@/components/ui/RiskPanel";
import { SignalFeed } from "@/components/ui/SignalFeed";
import { StatCard } from "@/components/ui/StatCard";
import { formatPct, formatUSD } from "@/lib/format";
import { market, portfolioApi, system } from "@/lib/api";
import { useStore } from "@/store";

const SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h"];

export default function DashboardPage() {
  const { portfolio, signals, riskStatus, status } = useStore((state) => ({
    portfolio: state.portfolio,
    signals: state.signals,
    riskStatus: state.riskStatus,
    status: state.status
  }));
  const setStatus = useStore((state) => state.setStatus);

  const [selectedSymbol, setSelectedSymbol] = useState("BTC_USDT");
  const [selectedTimeframe, setSelectedTimeframe] = useState("1h");
  const [busy, setBusy] = useState(false);

  const { data: equityData } = useSWR("equity", () => portfolioApi.equity(), { refreshInterval: 30000 });
  const { data: ohlcvData } = useSWR(
    ["ohlcv", selectedSymbol, selectedTimeframe],
    () => market.ohlcv(selectedSymbol, selectedTimeframe, 300),
    { refreshInterval: 15000 }
  );

  async function toggleTrading() {
    if (!status) {
      return;
    }
    setBusy(true);
    try {
      if (status.trading_active) {
        await system.stop();
        setStatus({ ...status, trading_active: false });
      } else {
        await system.start();
        setStatus({ ...status, trading_active: true });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Trading dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            {status ? `Cycle #${status.cycle_count} | ${status.trading_active ? "active" : "stopped"}` : "Loading system status"}
          </p>
        </div>
        <button
          className={`rounded-xl border px-4 py-2.5 text-sm font-semibold transition ${
            status?.trading_active
              ? "border-[#ff4466]/30 bg-[#ff4466]/10 text-[#ff7f99]"
              : "border-[#00ff88]/30 bg-[#00ff88]/10 text-[#00ff88]"
          }`}
          disabled={busy || !status}
          onClick={toggleTrading}
          type="button"
        >
          {busy ? "Working..." : status?.trading_active ? "Stop trading" : "Start trading"}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Portfolio value" value={formatUSD(portfolio?.total_value)} />
        <StatCard label="Unrealized PnL" value={formatUSD(portfolio?.unrealized_pnl)} pnl={portfolio?.unrealized_pnl} />
        <StatCard label="Realized PnL" value={formatUSD(portfolio?.realized_pnl)} pnl={portfolio?.realized_pnl} />
        <StatCard label="Win rate" value={formatPct(portfolio?.win_rate)} />
        <StatCard label="Profit factor" value={(portfolio?.profit_factor ?? 0).toFixed(2)} />
        <StatCard label="Total return" value={`${(portfolio?.total_pnl_pct ?? 0).toFixed(2)}%`} pnl={portfolio?.total_pnl_pct} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4 xl:col-span-2">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Equity curve</div>
          <EquityChart data={equityData ?? []} />
        </section>
        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Risk status</div>
          {riskStatus ? <RiskPanel risk={riskStatus} /> : <div className="text-sm text-slate-600">Loading risk state...</div>}
        </section>
      </div>

      <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Market</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-lg border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-sm text-white"
              onChange={(event) => setSelectedSymbol(event.target.value)}
              value={selectedSymbol}
            >
              {SYMBOLS.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
            <div className="flex overflow-hidden rounded-lg border border-[#1e1e2e]">
              {TIMEFRAMES.map((timeframe) => (
                <button
                  key={timeframe}
                  className={`px-3 py-2 text-xs transition ${
                    timeframe === selectedTimeframe ? "bg-[#00ff88]/10 text-[#00ff88]" : "text-slate-500 hover:text-slate-200"
                  }`}
                  onClick={() => setSelectedTimeframe(timeframe)}
                  type="button"
                >
                  {timeframe}
                </button>
              ))}
            </div>
          </div>
        </div>
        <CandlestickChart data={ohlcvData ?? []} />
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Open positions</div>
          <PositionsTable />
        </section>
        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Signal feed</div>
          <SignalFeed signals={signals.slice(0, 12)} />
        </section>
      </div>
    </div>
  );
}
