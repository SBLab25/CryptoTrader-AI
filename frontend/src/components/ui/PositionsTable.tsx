"use client";

import { formatPct, formatUSD, pnlClass } from "@/lib/format";
import { useStore } from "@/store";

export function PositionsTable() {
  const positions = useStore((state) => state.positions);

  if (!positions.length) {
    return <div className="py-10 text-center text-sm text-slate-600">No open positions</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
          <tr>
            <th className="pb-3">Symbol</th>
            <th className="pb-3 text-right">Entry</th>
            <th className="pb-3 text-right">Current</th>
            <th className="pb-3 text-right">Value</th>
            <th className="pb-3 text-right">PnL</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#1e1e2e]">
          {positions.map((position) => (
            <tr key={position.id}>
              <td className="py-3">
                <div className="text-white">{position.symbol}</div>
                <div className={`text-[11px] uppercase ${position.side === "long" ? "text-[#00ff88]" : "text-[#ff4466]"}`}>
                  {position.side}
                </div>
              </td>
              <td className="py-3 text-right text-slate-300">{formatUSD(position.entry_price)}</td>
              <td className="py-3 text-right text-white">{formatUSD(position.current_price)}</td>
              <td className="py-3 text-right text-slate-300">{formatUSD(position.usd_value)}</td>
              <td className={`py-3 text-right font-semibold ${pnlClass(position.unrealized_pnl)}`}>
                {formatUSD(position.unrealized_pnl)}
                <div className="text-[11px] opacity-70">{formatPct(position.unrealized_pnl_pct / 100)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
