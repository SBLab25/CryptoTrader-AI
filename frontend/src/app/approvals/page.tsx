"use client";

import { useEffect } from "react";

import { approvals as approvalsApi } from "@/lib/api";
import { countdown, formatUSD, timeAgo } from "@/lib/format";
import { useStore } from "@/store";

export default function ApprovalsPage() {
  const { approvals, setApprovals, updateApproval, addToast } = useStore((state) => ({
    approvals: state.approvals,
    setApprovals: state.setApprovals,
    updateApproval: state.updateApproval,
    addToast: state.addToast
  }));

  useEffect(() => {
    void approvalsApi.pending().then(setApprovals).catch(() => undefined);
  }, [setApprovals]);

  const pending = approvals.filter((item) => item.status === "pending");
  const resolved = approvals.filter((item) => item.status !== "pending");

  async function handleDecision(id: string, action: "approve" | "deny") {
    try {
      if (action === "approve") {
        await approvalsApi.approve(id);
        updateApproval(id, "approved");
      } else {
        await approvalsApi.deny(id);
        updateApproval(id, "denied");
      }
      addToast({
        title: action === "approve" ? "Trade approved" : "Trade denied",
        variant: action === "approve" ? "success" : "warning"
      });
    } catch (err) {
      addToast({
        title: "Approval action failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "error"
      });
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Approvals</h1>
        <p className="mt-1 text-sm text-slate-500">Human approval queue for higher-risk trades.</p>
      </div>

      <section className="space-y-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Pending</div>
        {!pending.length ? (
          <div className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-10 text-center text-sm text-slate-600">
            No pending approvals
          </div>
        ) : (
          pending.map((approval) => (
            <div key={approval.id} className="rounded-xl border border-[#ffaa00]/25 bg-[#111118] p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-semibold text-white">{approval.symbol}</span>
                    <span
                      className={`rounded px-2 py-0.5 text-[11px] uppercase ${
                        approval.side === "buy" ? "bg-[#00ff88]/10 text-[#00ff88]" : "bg-[#ff4466]/10 text-[#ff4466]"
                      }`}
                    >
                      {approval.side}
                    </span>
                    <span className="font-semibold text-white">{formatUSD(approval.usd_amount)}</span>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    <Info label="Strategy" value={approval.strategy} />
                    <Info label="Confidence" value={`${(approval.confidence * 100).toFixed(0)}%`} />
                    <Info label="Risk reward" value={`1:${approval.risk_reward.toFixed(2)}`} />
                  </div>
                  <div className="rounded-xl border border-[#1e1e2e] bg-[#0d0d14] p-3 text-sm text-slate-400">
                    {approval.reasoning}
                  </div>
                </div>
                <div className="min-w-40 space-y-3 text-right">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Expires in</div>
                    <div className="mt-1 text-xl font-semibold text-[#ffaa00]">{countdown(approval.expires_at)}</div>
                  </div>
                  <div className="space-x-2">
                    <button
                      className="rounded-lg border border-[#ff4466]/30 bg-[#ff4466]/10 px-4 py-2 text-sm text-[#ff7f99]"
                      onClick={() => handleDecision(approval.id, "deny")}
                      type="button"
                    >
                      Deny
                    </button>
                    <button
                      className="rounded-lg border border-[#00ff88]/30 bg-[#00ff88]/10 px-4 py-2 text-sm text-[#00ff88]"
                      onClick={() => handleDecision(approval.id, "approve")}
                      type="button"
                    >
                      Approve
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </section>

      {resolved.length ? (
        <section className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
          <div className="mb-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">Recent decisions</div>
          <div className="space-y-2">
            {resolved.slice(0, 20).map((approval) => (
              <div key={approval.id} className="flex items-center justify-between rounded-lg border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2">
                <div>
                  <div className="text-sm text-white">{approval.symbol}</div>
                  <div className="text-[11px] text-slate-500">{timeAgo(approval.created_at)}</div>
                </div>
                <div className="text-sm text-slate-300">{formatUSD(approval.usd_amount)}</div>
                <div className="text-xs uppercase text-slate-400">{approval.status}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-white">{value}</div>
    </div>
  );
}
