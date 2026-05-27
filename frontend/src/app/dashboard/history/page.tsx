"use client";

import useSWR from "swr";

import { PnLBySymbolChart } from "@/components/charts/PnLBySymbol";
import { formatPct, formatUSD, pnlClass, timeAgo } from "@/lib/format";
import { portfolioApi } from "@/lib/api";

export default function HistoryPage() {
  const { data: trades } = useSWR("trade-history", () => portfolioApi.trades(100), { refreshInterval: 30000 });
  const { data: pnlBySymbol } = useSWR("pnl-symbol", portfolioApi.pnlSymbol, { refreshInterval: 60000 });

  const closed = (trades ?? []).filter((trade) => trade.status.toLowerCase() === "closed" || trade.status.toLowerCase() === "filled");
  const wins = closed.filter((trade) => (trade.realized_pnl ?? 0) > 0);
  const totalPnL = closed.reduce((sum, trade) => sum + (trade.realized_pnl ?? 0), 0);
  const winRate = closed.length ? wins.length / closed.length : 0;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Trade history</h1>
        <p className="mt-1 text-sm text-slate-500">{closed.length} closed trades</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryCard label="Total PnL" value={formatUSD(totalPnL)} pnl={totalPnL} />
        <SummaryCard label="Win rate" value={formatPct(winRate)} />
        <SummaryCard label="Wins" value={`${wins.length}`} />
        <SummaryCard label="Losses" value={`${closed.length - wins.length}`} />
      </div>

      <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
        <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">PnL by symbol</div>
        <PnLBySymbolChart data={pnlBySymbol ?? []} />
      </section>

      <section className="overflow-hidden rounded-xl border border-[#1e1e2e] bg-[#111118]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#0d0d14] text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <tr>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Strategy</th>
              <th className="px-4 py-3 text-right">Entry</th>
              <th className="px-4 py-3 text-right">Exit</th>
              <th className="px-4 py-3 text-right">PnL</th>
              <th className="px-4 py-3 text-right">Opened</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e1e2e]">
            {closed.map((trade) => (
              <tr key={trade.id}>
                <td className="px-4 py-3 text-white">{trade.symbol}</td>
                <td className="px-4 py-3 text-slate-400">{trade.strategy}</td>
                <td className="px-4 py-3 text-right text-slate-300">{formatUSD(trade.entry_price)}</td>
                <td className="px-4 py-3 text-right text-slate-300">{formatUSD(trade.exit_price)}</td>
                <td className={`px-4 py-3 text-right font-semibold ${pnlClass(trade.realized_pnl)}`}>
                  {formatUSD(trade.realized_pnl)}
                  {trade.realized_pnl_pct !== null ? (
                    <div className="text-[11px] opacity-70">{formatPct((trade.realized_pnl_pct ?? 0) / 100)}</div>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-right text-slate-500">{timeAgo(trade.opened_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function SummaryCard({ label, value, pnl }: { label: string; value: string; pnl?: number }) {
  return (
    <div className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${pnl === undefined ? "text-white" : pnlClass(pnl)}`}>{value}</div>
    </div>
  );
}
