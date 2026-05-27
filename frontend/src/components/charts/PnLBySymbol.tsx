"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function PnLBySymbolChart({ data }: { data: { symbol: string; pnl: number; trades: number }[] }) {
  if (!data.length) {
    return <div className="py-8 text-center text-sm text-slate-600">No closed trades yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <XAxis dataKey="symbol" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: "#111118", border: "1px solid #1e1e2e", borderRadius: 10 }}
          formatter={(value: number) => [`$${value.toFixed(2)}`, "PnL"]}
        />
        <Bar dataKey="pnl" radius={[6, 6, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.symbol} fill={entry.pnl >= 0 ? "#00ff88" : "#ff4466"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
