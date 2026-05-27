"use client";

import { risk } from "@/lib/api";
import { formatPct } from "@/lib/format";
import { useStore } from "@/store";
import type { RiskStatus } from "@/types";

export function RiskPanel({ risk: riskStatus }: { risk: RiskStatus }) {
  const setRiskStatus = useStore((state) => state.setRiskStatus);
  const addToast = useStore((state) => state.addToast);

  async function handleResume() {
    try {
      await risk.resume();
      setRiskStatus({ ...riskStatus, paused: false, pause_reason: null });
      addToast({ title: "Risk engine resumed", variant: "success" });
    } catch (err) {
      addToast({
        title: "Resume failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "error"
      });
    }
  }

  return (
    <div className="space-y-3 text-sm">
      {riskStatus.paused ? (
        <div className="rounded-xl border border-[#ff4466]/30 bg-[#ff4466]/10 p-3">
          <div className="font-semibold text-[#ff7f99]">Trading paused</div>
          <div className="mt-1 text-xs text-[#ffb3c2]">{riskStatus.pause_reason || "Risk rules engaged."}</div>
          <button className="mt-2 text-xs text-white underline" onClick={handleResume} type="button">
            Resume
          </button>
        </div>
      ) : null}

      <RiskRow label="Daily loss" value={formatPct(riskStatus.daily_loss_pct)} />
      <RiskRow label="Drawdown" value={formatPct(riskStatus.current_drawdown)} />
      <RiskRow label="Open positions" value={`${riskStatus.open_positions}`} />
      <RiskRow label="Circuit breaker" value={riskStatus.circuit_breaker_state} />
      <RiskRow label="Correlation graph" value={`${riskStatus.correlation_graph_nodes} assets`} />
    </div>
  );
}

function RiskRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-200">{value}</span>
    </div>
  );
}
