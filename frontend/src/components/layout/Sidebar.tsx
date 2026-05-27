"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { auth } from "@/lib/api";
import { useStore } from "@/store";
import type { TradingMode } from "@/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/approvals", label: "Approvals" },
  { href: "/training", label: "Training" },
  { href: "/dashboard/history", label: "History" }
];

const MODE_STYLES: Record<TradingMode, string> = {
  demo: "border-[#4488ff]/30 bg-[#4488ff]/10 text-[#4488ff]",
  paper: "border-[#ffaa00]/30 bg-[#ffaa00]/10 text-[#ffaa00]",
  live: "border-[#00ff88]/30 bg-[#00ff88]/10 text-[#00ff88]"
};

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { status, connected, approvals } = useStore((state) => ({
    status: state.status,
    connected: state.connected,
    approvals: state.approvals
  }));

  async function signOut() {
    await auth.logout();
    router.replace("/login");
  }

  const mode = (status?.mode ?? "paper") as TradingMode;
  const pendingCount = approvals.filter((item) => item.status === "pending").length;

  return (
    <aside className="sticky top-0 flex h-screen w-60 flex-shrink-0 flex-col border-r border-[#1e1e2e] bg-[#0d0d14]">
      <div className="border-b border-[#1e1e2e] px-5 py-5">
        <div className="text-xs font-mono uppercase tracking-[0.24em] text-[#00ff88]">CryptoTraderAI</div>
        <div className="mt-2 text-2xl font-semibold text-white">v2 Dashboard</div>
      </div>

      <div className="border-b border-[#1e1e2e] px-5 py-3">
        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-mono uppercase ${MODE_STYLES[mode]}`}>
          {mode}
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const badge = item.href === "/approvals" ? pendingCount : 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "bg-[#00ff88]/10 text-[#00ff88]"
                  : "text-slate-400 hover:bg-[#141420] hover:text-slate-200"
              }`}
            >
              <span>{item.label}</span>
              {badge > 0 ? (
                <span className="rounded-full bg-[#ff4466] px-2 py-0.5 text-[11px] font-semibold text-white">
                  {badge}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-[#1e1e2e] px-5 py-4">
        <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-[#00ff88]" : "bg-[#ff4466]"}`} />
          {connected ? "Live feed connected" : "Feed disconnected"}
        </div>
        <div className="mt-2 text-[11px] text-slate-600">
          {status ? `${status.llm_provider} / ${status.llm_model}` : "Waiting for system status"}
        </div>
        <button
          className="mt-4 text-sm text-slate-400 transition hover:text-[#ff4466]"
          onClick={signOut}
          type="button"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
