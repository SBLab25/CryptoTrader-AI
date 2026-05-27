"use client";

import { timeAgo } from "@/lib/format";
import type { Signal } from "@/types";

export function SignalFeed({ signals }: { signals: Signal[] }) {
  if (!signals.length) {
    return <div className="py-10 text-center text-sm text-slate-600">Waiting for signals...</div>;
  }

  return (
    <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
      {signals.map((signal) => (
        <div key={signal.id} className="rounded-xl border border-[#1e1e2e] bg-[#0d0d14] p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-[11px] font-semibold uppercase ${
                  signal.direction === "buy"
                    ? "bg-[#00ff88]/10 text-[#00ff88]"
                    : signal.direction === "sell"
                      ? "bg-[#ff4466]/10 text-[#ff4466]"
                      : "bg-[#1e1e2e] text-slate-400"
                }`}
              >
                {signal.direction}
              </span>
              <span className="text-sm font-medium text-white">{signal.symbol}</span>
            </div>
            <span className="text-[11px] text-slate-500">{timeAgo(signal.timestamp)}</span>
          </div>
          <div className="mt-2 text-xs text-slate-400">{signal.reasoning}</div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
            <span>{signal.strategy}</span>
            <span>{(signal.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
