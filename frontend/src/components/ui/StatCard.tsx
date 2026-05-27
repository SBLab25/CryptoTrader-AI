import { clsx } from "clsx";

export function StatCard({
  label,
  value,
  pnl,
  inverse
}: {
  label: string;
  value: string;
  pnl?: number | null;
  inverse?: boolean;
}) {
  const tone =
    pnl === undefined || pnl === null
      ? "text-white"
      : inverse
        ? pnl > 0
          ? "text-[#ff4466]"
          : "text-[#00ff88]"
        : pnl > 0
          ? "text-[#00ff88]"
          : pnl < 0
            ? "text-[#ff4466]"
            : "text-white";

  return (
    <div className="rounded-xl border border-[#1e1e2e] bg-[#111118] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className={clsx("mt-2 text-lg font-semibold tabular-nums", tone)}>{value}</div>
    </div>
  );
}
